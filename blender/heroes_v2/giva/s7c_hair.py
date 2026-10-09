"""Stage 7c: Giva's built-in default hair "waves" (master concept: lush dark-brown waves past the shoulders, centre
parting, volume at the sides, framing the face).

Guide strands are grown from the centre parting (front hairline -> crown) and from a fan at the crown, hugging a skull
proxy away from the parting and then falling under gravity with collision against the head, suit and gear (face locks in
front of the shoulders, the rest behind). Two continuous layered SHEETS are lofted across neighbouring guides (an
underlayer that hides the scalp, then a second layer), and wavy CLUMP cards sit on top; neighbouring guides wave in phase
so the layers move as one mass. The strand atlas (dense sheet strands + four tapered clump strips, fake anisotropic sheen
band, darker roots) is painted procedurally (no external images). Custom normals point out of the hair volume.
Weights: Head on the skull, blending to Neck / Spine2 towards the tips.

  blender -b out/giva_face.blend --python s7c_hair.py
Saves out/giva_hair.blend (mesh Hair_waves, material Hair_waves, texture out/tex/Hair_waves_Color.png).
"""
import bpy, sys, os, math, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import gv
importlib.reload(gv)
P = gv.P
A = gv.args()
RNG = np.random.default_rng(int(gv.opt(A, "--seed", "7")))
rig = bpy.data.objects[gv.RIG]
body = bpy.data.objects["Body"]
TEX = os.path.join(gv.OUT, "tex")
NAME = "Hair_waves"
ATLAS = 2048
STRIPS = 8

XB = gv.basis_co(body)
TB = gv.tri_index(body.data)
bones = rig.data.bones
HEAD_H = np.array(bones[P + "Head"].head_local)
HEAD_T = np.array(bones[P + "Head"].tail_local)
HEAD_TOP = float(XB[:, 2].max())


def group_ids(o, name, thr=0.5):
    g = o.vertex_groups.get(name)
    return np.array([v.index for v in o.data.vertices for e in v.groups if e.group == g.index and e.weight > thr])


# ----------------------------------------------------------------------------- skull proxy (smooth ellipsoid)
scalp_ids = group_ids(body, "scalp")
ear_ids = group_ids(body, "ears")
head_pts = XB[(XB[:, 2] > 1.585) & (np.abs(XB[:, 0]) < 0.11)]
C0 = np.array((0.0, (head_pts[:, 1].min() + head_pts[:, 1].max()) / 2 + 0.004, 1.646))
R0 = np.array((0.083, 0.102, 0.092))
pts_fit = XB[scalp_ids]
k = np.percentile(np.sqrt((((pts_fit - C0) / R0) ** 2).sum(1)), 35)
RAD = R0 * k
_hv = np.where(XB[:, 2] > 1.5)[0]
_hs = set(_hv.tolist())
_ht = np.array([t for t in TB if t[0] in _hs and t[1] in _hs and t[2] in _hs])
HEADBVH = BVHTree.FromPolygons([Vector(c) for c in XB], _ht.tolist(), all_triangles=True)


def ell_project(p, off):
    """Head surface point along the ray from the skull centre: the farther of a smooth ellipsoid (fitted inside the
    scalp) and the real head (ears, occiput), plus `off`; normal from the ellipsoid (smooth flow)."""
    d = gv.nrm(p - C0)
    r = RAD
    t_e = 1.0 / math.sqrt(((d / r) ** 2).sum())
    loc, nrm, fi, dist = HEADBVH.ray_cast(Vector(C0), Vector(d), 0.3)
    t_b = dist if loc is not None else 0.0
    t_ = max(t_e, t_b) + off
    q = C0 + d * t_
    qe = C0 + d * t_e
    n = gv.nrm((qe - C0) / (r * r))
    return q, n


# ----------------------------------------------------------------------------- collision (body + suit + gear)
def bvh_of(objs):
    V, T = [], []
    off = 0
    for o in objs:
        X = gv.basis_co(o)
        tri = gv.tri_index(o.data)
        V.append(X)
        T.append(tri + off)
        off += len(X)
    V = np.concatenate(V)
    T = np.concatenate(T)
    return BVHTree.FromPolygons([Vector(c) for c in V], T.tolist(), all_triangles=True)


COLL = bvh_of([o for o in (bpy.data.objects.get(n) for n in ("Body", "Top", "ShoulderR", "Harness", "Visor")) if o])


_SP = []
for _b in ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"):
    _SP.append(np.array(bones[P + _b].head_local))
_SP.append(HEAD_T)
_SP = np.array(_SP)


def axis_at(z):
    return np.array((np.interp(z, _SP[:, 2], _SP[:, 0]), np.interp(z, _SP[:, 2], _SP[:, 1]), z))


def collide(p, margin):
    loc, nrm, fi, dist = COLL.find_nearest(Vector(p), 0.25)
    if loc is None:
        return p, None
    loc = np.array(loc)
    n = np.array(nrm)
    # inward-facing walls (the collar's inner side, plate undersides) count as their outer side
    ax = axis_at(loc[2])
    if n @ (loc - ax) < 0 and np.linalg.norm((loc - ax)[:2]) > 0.02:
        n = -n
    d = p - loc
    s = d @ n
    if s < margin:
        p = p + n * (margin - s)
    # never inside the skull proxy either
    if p[2] > 1.585:
        q, ne = ell_project(p, 0.0)
        if np.linalg.norm(p - C0) < np.linalg.norm(q - C0) + margin * 0.6:
            p = q + gv.nrm(q - C0) * margin * 0.6
    return p, n


# ----------------------------------------------------------------------------- growth
def grow(root, off, length, side, front, rng, step=0.005, d0=None, lift=0.0):
    """Strand polyline from a scalp root: hugs the skull (offset `off`) away from the centre parting, then falls
    with gravity and collisions; `front` locks go in front of the shoulder, others behind."""
    p, n = ell_project(root, off)
    pts = [p]
    # initial direction: sideways from the parting near the top/front, downwards (and a little back) elsewhere
    top = np.clip((root[2] - 1.66) / 0.06, 0, 1)
    fr = np.clip((-root[1] - 0.02) / 0.08, 0, 1)
    d = gv.nrm(np.array((side * (0.35 + 0.9 * top + 0.7 * fr), 0.05 + 0.25 * (1 - fr) + 0.4 * fr, -0.6 - 0.4 * (1 - top) + 0.3 * fr)))
    if d0 is not None:
        d = gv.nrm(np.asarray(d0, float))
    on_skull = True
    s = 0.0
    while s < length:
        if on_skull:
            q, nq = ell_project(p, off)
            d = d - nq * (d @ nq)
            d = gv.nrm(d + np.array((0, 0, -0.16)))
            if p[1] < C0[1] - 0.05 and abs(p[0]) < 0.075 and p[2] < 1.71:
                d = gv.nrm(d + np.array((side * 0.9, 0.6, 0.15)))            # never down over the forehead/face
            # sleek crown, volume from the temples down (concept): layer offsets shrink near the top of the head
            crown = 0.4 + 0.6 * gv.ss(1.705, 1.64, p[2])
            p2, n2 = ell_project(p + d * step, (off + lift * gv.ss(0.02, 0.1, s)) * crown)
            # leave the skull where its surface turns to face down / below the ear line
            if n2[2] < -0.25 or p2[2] < 1.6 - 0.02 * (1 - abs(side)):
                on_skull = False
                # leave the head with some spring: arc out over the collar instead of folding onto its rim
                rad0 = p2 - axis_at(p2[2])
                rad0[2] = 0.0
                if np.linalg.norm(rad0) > 1e-3:
                    lat = abs(gv.nrm(rad0)[0])
                    d = gv.nrm(d + gv.nrm(rad0) * (0.12 + 0.3 * lat))
            p_new = p2
        else:
            bias = np.array((0.0, 0.0, -1.0))
            if front and p[2] > 1.38 and (abs(p[0]) > 0.075 or p[2] < 1.5):
                bias = bias + np.array((side * 0.12, -0.55, 0.0))
            elif not front and p[2] > 1.4:
                bias = bias + np.array((side * 0.05, 0.16, 0.0))
            rad = p - axis_at(p[2])
            rad[2] = 0.0
            r_ = np.linalg.norm(rad)
            lat = abs(rad[0]) / max(r_, 1e-6)                                    # sides puff out, the back drapes
            bias = bias + gv.nrm(rad) * 0.4 * lat * gv.ss(1.32, 1.5, p[2]) * (1 - gv.ss(1.52, 1.6, p[2])) * (r_ < 0.15)
            if r_ > 0.17 and p[2] > 1.3:
                bias = bias - gv.nrm(rad) * 0.5                                  # no strands sticking out sideways
            # keep the face clear: anything in front of the face is steered out to its side
            if p[2] > 1.49 and abs(p[0]) < 0.085 and p[1] < C0[1] - 0.03:
                bias = bias + np.array((side * 1.2, 0.3, 0.0))
            d = gv.nrm(d * 0.8 + bias * 0.32)
            p_try = p + d * step
            p_new, n_c = collide(p_try, 0.008 + off)
            if n_c is not None and np.linalg.norm(p_new - p_try) > 1e-5:
                # in contact: slide along the surface (hair flows over collars, shoulders and plates)
                dt = d - n_c * (d @ n_c)
                if np.linalg.norm(dt) < 0.2:
                    dt = dt + gv.nrm(np.array((side * 0.3, 0.6 if not front else -0.6, 0.0))) * 0.5
                p_new, _ = collide(p + gv.nrm(dt) * step, 0.008 + off)
        d = gv.nrm(p_new - p)
        s += np.linalg.norm(p_new - p)
        p = p_new
        pts.append(p)
        if len(pts) > 400:
            break
    P_ = np.array(pts)
    # relax (keep the root), re-collide
    for it in range(8):
        P_[1:-1] = 0.5 * P_[1:-1] + 0.25 * (P_[:-2] + P_[2:])
        P_[-1] = 0.5 * P_[-1] + 0.5 * P_[-2] + (P_[-2] - P_[-3]) * 0.5
        if it % 2 == 1:
            for i in range(1, len(P_)):
                P_[i], _ = collide(P_[i], 0.006 + off)
    return P_


def resample(P_, n):
    seg = np.linalg.norm(np.diff(P_, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, s[-1], n)
    return np.stack([np.interp(u, s, P_[:, j]) for j in range(3)], 1), u


def outward(p):
    """Outward direction for card orientation: from the skull centre near the head, else the collision normal."""
    if p[2] > 1.56:
        return gv.nrm(p - C0)
    loc, nrm, fi, dist = COLL.find_nearest(Vector(p), 0.3)
    return gv.nrm(np.array(nrm)) if nrm is not None else gv.nrm(p - C0)


def wave(P_, s, amp, lam, phase, start=0.14):
    """S-curve waves: side-to-side in the hair surface plus in/out of it (a flattened helix, so the waves show both
    from the front and from the side); amplitude ramps in below the ears and grows a little towards the ends."""
    out = P_.copy()
    T = gv.nrm(np.gradient(P_, axis=0))
    L = s[-1] if s[-1] > 0 else 1.0
    for i in range(len(P_)):
        o = outward(P_[i])
        o = o - T[i] * (o @ T[i])
        o = gv.nrm(o) if np.linalg.norm(o) > 1e-4 else outward(P_[i])
        b = gv.nrm(np.cross(T[i], o))
        a = amp * gv.ss(start, start + 0.12, s[i]) * (1 + 0.35 * (s[i] / L))
        th = 2 * math.pi * s[i] / lam + phase
        out[i] = P_[i] + b * a * math.sin(th) + o * a * 0.35 * (math.cos(th) + 0.8)
    return out


# ----------------------------------------------------------------------------- parting + guides
SHEET_U = 0.5            # atlas: u < 0.5 dense sheet strands, u >= 0.5 four clump strips
SHEET_W = 0.10           # metres of hair width the sheet region represents
CLUMP_STRIPS = 4
T_SPLIT = 0.42           # parting guides in front of this fall in front of the shoulders (face framing)

scalp_ids_ = scalp_ids
SC = XB[scalp_ids_]
_mid = SC[np.abs(SC[:, 0]) < 0.012]
PF = _mid[np.argmin(_mid[:, 1])]                              # front hairline on the centre line
_top = _mid[_mid[:, 2] > _mid[:, 2].max() - 0.035]
PC = _top[np.argmax(_top[:, 1])]                              # crown (back end of the parting)


def parting(t):
    q, n = ell_project(PF * (1 - t) + PC * t + np.array((0, 0, 0.04)) * math.sin(math.pi * t), 0.0)
    return q


def guide_specs(side, n_part=22, n_fan=10):
    """Ordered (front -> back) guide roots and start directions for one side."""
    out = []
    for t in np.linspace(0.0, 1.0, n_part):
        root = parting(t) - np.array((side * 0.005, 0, 0))     # each side starts just across the parting: no slit
        d0 = np.array((side * 1.0, -0.42 * (1 - t) + 0.25 * t, -0.25 - 0.2 * t))
        out.append(dict(root=root, d0=d0, front=t < T_SPLIT, t=t))
    for k in range(1, n_fan + 1):
        ph = math.radians(90 + 90 * k / n_fan)
        d0 = np.array((side * math.sin(ph), -math.cos(ph) * 1.0, -0.35))
        out.append(dict(root=parting(1.0) - np.array((side * 0.005 * (1 - k / n_fan), 0, 0)), d0=d0, front=False,
                        t=1.0 + k / n_fan))
    return out


def length_for(spec, rng, jitter=0.02):
    base = 0.47 if spec["front"] else (0.5 + 0.08 * min(1.0, max(0.0, spec["t"] - 0.6)))
    return base + rng.uniform(-jitter, jitter)


def grow_guide(spec, side, off, lift, rng, jitter=0.02):
    return grow(spec["root"], off, length_for(spec, rng, jitter), side, spec["front"], rng, d0=spec["d0"], lift=lift)


def phase_of(spec, side):
    return 0.55 * spec["t"] * 3.0 + (0.0 if side > 0 else 1.7)


def finish_strand(P_, K, off, amp, lam, phase, start=0.14):
    # waves are applied on a dense polyline (8+ samples per wavelength), then resampled to the mesh rows
    Q, s = resample(P_, 120)
    Q = wave(Q, s, amp, lam, phase, start)
    for i in range(1, len(Q)):
        Q[i], _ = collide(Q[i], 0.005 + off)
    Q[1:-1] = 0.8 * Q[1:-1] + 0.1 * (Q[:-2] + Q[2:])
    return resample(Q, K + 1)


# ----------------------------------------------------------------------------- mesh assembly
LAYER_DEPTH = {0: 1.0, 1: 0.65, 2: 0.4, 3: 0.15, 4: 0.0}   # underlayer .. flyaways


class Mesh:
    def __init__(self):
        self.V, self.F, self.UV, self.N, self.Z, self.L = [], [], [], [], [], []
        self.ST = []                       # strand data: (root->tip 0..1, depth in the hair mass 0 outer..1 inner)
        self.layer = 0

    def strip(self, L, R, s, uL, uR, nrm_out, bulge=0.0015, across=3):
        """Quad strip between two polylines (same row count), 3 verts across (centre bulges out) or 2. Each strip gets its
        own small shading-normal tilt about the strand (neighbouring strips catch the anisotropic highlight at different
        heights, so the hair mass never shades as one smooth sheet)."""
        base = len(self.V)
        K = len(L)
        Lt = s[-1] if s[-1] > 0 else 1.0
        Tm = gv.nrm(np.gradient(0.5 * (L + R), axis=0))
        tilt = RNG.normal(0, 0.28)
        for i in range(K):
            M = 0.5 * (L[i] + R[i])
            o = shade_normal(M, Tm[i])
            bn = gv.nrm(np.cross(Tm[i], o))
            o = gv.nrm(o * math.cos(tilt) + bn * math.sin(tilt))
            cols = ((0.0, L[i]), (0.5, M + o * bulge), (1.0, R[i])) if across == 3 else ((0.0, L[i]), (1.0, R[i]))
            for x, P_ in cols:
                self.V.append(P_)
                self.UV.append((uL + (uR - uL) * x, 0.985 - 0.97 * s[i] / Lt))
                self.ST.append((s[i] / Lt, LAYER_DEPTH.get(self.layer, 0.3)))
                self.N.append(o)
                self.Z.append(P_[2])
        for i in range(K - 1):
            for j in range(across - 1):
                a = base + i * across + j
                self.F.append((a, a + 1, a + 1 + across, a + across))
                self.L.append(self.layer)

    def card(self, Q, s, w0, w1, uL, uR, nrm_out, twist=0.0):
        T = gv.nrm(np.gradient(Q, axis=0))
        L, R = [], []
        Lt = s[-1]
        b_prev = None
        for i in range(len(Q)):
            o = nrm_out(Q[i])
            o_p = o - T[i] * (o @ T[i])
            b_ideal = gv.nrm(np.cross(T[i], o_p)) if np.linalg.norm(o_p) > 1e-3 else None
            if b_prev is None:
                b = b_ideal if b_ideal is not None else gv.nrm(np.cross(T[i], np.array((0, 0, 1.0))))
            else:
                # parallel transport (no flips where the strand runs along the outward direction) pulled towards
                # the outward-facing orientation only where that is well defined
                bt = b_prev - T[i] * (b_prev @ T[i])
                bt = gv.nrm(bt) if np.linalg.norm(bt) > 1e-6 else b_prev
                if b_ideal is not None:
                    if b_ideal @ bt < 0:
                        b_ideal = -b_ideal
                    wgt = float(np.clip((np.linalg.norm(o_p) - 0.35) / 0.4, 0, 1)) * 0.5
                    b = gv.nrm(bt * (1 - wgt) + b_ideal * wgt)
                else:
                    b = bt
            b_prev = b
            tw = twist * gv.ss(0.15, 0.5, s[i] / Lt)
            b = gv.nrm(b * math.cos(tw) + o * math.sin(tw))
            w = (w0 + (w1 - w0) * (s[i] / Lt) ** 1.1) * (0.75 + 0.25 * gv.ss(0.0, 0.08, s[i] / Lt))
            L.append(Q[i] - b * w / 2)
            R.append(Q[i] + b * w / 2)
        self.strip(np.array(L), np.array(R), s, uL, uR, nrm_out, bulge=0.002)


def shade_normal(p, T):
    """Shading normal of the hair volume: out of the skull on the head, horizontally out of the body axis where the hair
    hangs (never the up-facing shoulder/suit normal, which lit hanging cards like a grey veil), orthogonal to the strand."""
    rad = p - axis_at(p[2])
    rad[2] = 0.0
    hang = gv.nrm(rad) if np.linalg.norm(rad) > 1e-3 else gv.nrm(p - C0)
    k = gv.ss(1.56, 1.63, p[2])
    o = gv.nrm(gv.nrm(p - C0) * k + hang * (1 - k))
    o = o - T * (o @ T)
    return gv.nrm(o) if np.linalg.norm(o) > 1e-4 else hang


def nrm_out(p):
    o = outward(p)
    rad = p - axis_at(p[2])
    rad[2] = 0.0
    if p[2] < 1.6 and np.linalg.norm(rad) > 1e-3:
        o = gv.nrm(o * 0.5 + gv.nrm(rad) * 0.5)
    return o


def sheet_u(rng, width):
    w = float(np.clip(width / SHEET_W * SHEET_U, 0.05, SHEET_U - 0.02))
    u0 = rng.uniform(0.005, SHEET_U - w - 0.005)
    return u0, u0 + w


def clump_u(rng):
    c = int(rng.integers(0, CLUMP_STRIPS))
    w = (1.0 - SHEET_U) / CLUMP_STRIPS
    return SHEET_U + c * w + 0.004, SHEET_U + (c + 1) * w - 0.004


def build_sheet(mesh, side, off, lift, amp, rng, K=34):
    specs = guide_specs(side, n_part=20, n_fan=9)
    strands = []
    for sp in specs:
        P_ = grow_guide(sp, side, off, lift, rng, jitter=0.01)
        Q, s = finish_strand(P_, K, off, amp, 0.12, phase_of(sp, side))
        strands.append((sp, Q, s))
    # loft neighbours; the front/back split gets its own boundary (the shoulders separate the two curtains)
    n = 0
    for (a, Qa, sa), (b, Qb, sb) in zip(strands[:-1], strands[1:]):
        if a["front"] != b["front"]:
            continue
        ws = np.linalg.norm(Qa - Qb, axis=1)
        if ws.max() > 0.1 or (ws.max() > 0.06 and ws[K // 2:].max() > 4.0 * max(ws[K // 4], 0.012) + 0.03):
            continue                          # never bridge a gap (hair parted around a shoulder or the ear)
        width = float(ws[K // 2])
        uL, uR = sheet_u(rng, width)
        s = 0.5 * (sa + sb)
        mesh.strip(Qa, Qb, s, uL, uR, nrm_out, across=2)
        n += 1
    return n, strands


def bridge_back(mesh, left, right, rng):
    """Close the back centre: strip between the last (straight-back) guides of the two sides."""
    (_, Qa, sa), (_, Qb, sb) = left[-1], right[-1]
    ws = np.linalg.norm(Qa - Qb, axis=1)
    if ws.max() < 0.07:
        uL, uR = sheet_u(rng, float(ws[len(ws) // 2]) + 0.01)
        mesh.strip(Qa, Qb, 0.5 * (sa + sb), uL, uR, nrm_out, across=2)
        return 1
    return 0


def build():
    mesh = Mesh()
    rng = RNG
    nsheets = 0
    guides = []
    # three continuous layers: underlayer (hides the scalp, darker roots), main layer and an outer volume layer with
    # more lift (fuller crown and sides, concept)
    for li, (off, lift, amp) in enumerate(((0.0035, 0.008, 0.009), (0.009, 0.016, 0.012), (0.0135, 0.022, 0.013))):
        mesh.layer = li
        per_side = {}
        for side in (-1.0, 1.0):
            n, strands = build_sheet(mesh, side, off, lift, amp, rng)
            nsheets += n
            per_side[side] = strands
            guides += [(side, st) for st in strands]
        nsheets += bridge_back(mesh, per_side[-1.0], per_side[1.0], rng)
    gv.log(NAME, "sheet strips", nsheets)
    mesh.layer = 2
    # clump cards on top: one per guide (jittered between neighbours), wider at the sides, extra face-framing locks
    ncl = 0
    for side in (-1.0, 1.0):
        specs = guide_specs(side, n_part=18, n_fan=9)
        for k, sp in enumerate(specs):
            for rep in range(2 if sp["front"] else 1):
                j = dict(sp)
                j["root"] = sp["root"] + rng.normal(0, 0.003, 3) * np.array((1, 1, 0.3))
                j["d0"] = sp["d0"] + rng.normal(0, 0.12, 3)
                off = 0.017 + 0.003 * rep
                P_ = grow(j["root"], off, length_for(sp, rng, 0.05) - rng.uniform(0, 0.04), side, sp["front"], rng,
                          d0=j["d0"], lift=0.024)
                if len(P_) < 6:
                    continue
                radial = np.linalg.norm((P_ - np.array([axis_at(z) for z in P_[:, 2]]))[:, :2], axis=1)
                if radial.max() > 0.26 or P_[:, 2].max() > HEAD_TOP + 0.03:
                    continue
                Q, s = finish_strand(P_, 24, off, rng.uniform(0.012, 0.015), rng.uniform(0.11, 0.13),
                                     phase_of(sp, side) + rng.normal(0, 0.15))
                uL, uR = clump_u(rng)
                mesh.card(Q, s, rng.uniform(0.036, 0.046), rng.uniform(0.018, 0.026), uL, uR, nrm_out,
                          twist=rng.uniform(-0.15, 0.15))
                ncl += 1
    gv.log(NAME, "clump cards", ncl)
    # flyaways: a few fine loose strands along the lengths at the silhouette (never at the crown): each follows a
    # piece of a sheet guide, lifted off it by 4-10 mm with its own looser wave (narrow cards: 1-3 strands of a clump)
    mesh.layer = 4
    nfl = 0
    pool = [st for side_, st in guides]
    for k in range(34):
        sp, Q0, s0 = pool[int(rng.integers(0, len(pool)))]
        n0 = len(Q0)
        i0 = int(n0 * rng.uniform(0.3, 0.55))
        i1 = min(n0 - 1, i0 + int(n0 * rng.uniform(0.3, 0.45)))
        seg = Q0[i0:i1 + 1].copy()
        if len(seg) < 5 or seg[:, 2].max() > 1.6:
            continue
        o_ = np.array([nrm_out(p_) for p_ in seg])
        lift_ = rng.uniform(0.004, 0.01) * np.sin(np.linspace(0.15, 1.0, len(seg)) * math.pi * 0.5)
        seg = seg + o_ * lift_[:, None]
        Q, s_ = resample(seg, 12)
        Q = wave(Q, s_, rng.uniform(0.004, 0.008), rng.uniform(0.05, 0.07), rng.uniform(0, 6.3), start=0.0)
        c0, c1 = clump_u(rng)
        w_ = (c1 - c0) * rng.uniform(0.12, 0.2)
        u0 = rng.uniform(c0, c1 - w_)
        mesh.card(Q, s_, rng.uniform(0.004, 0.007), 0.002, u0, u0 + w_, nrm_out, twist=rng.uniform(-0.4, 0.4))
        nfl += 1
    gv.log(NAME, "flyaways", nfl)
    V = np.array(mesh.V)
    o = gv.mesh_obj(NAME, V, mesh.F)
    me = o.data
    uv = me.uv_layers.new(name="UVMap")
    loop_uv = np.array([mesh.UV[me.loops[li].vertex_index] for f in me.polygons for li in f.loop_indices], np.float32)
    uv.data.foreach_set("uv", loop_uv.ravel())
    st = me.uv_layers.new(name="Strand")             # FBX second UV set -> Unity TEXCOORD1 (EOA/Hair _STRAND_DATA)
    loop_st = np.array([mesh.ST[me.loops[li].vertex_index] for f in me.polygons for li in f.loop_indices], np.float32)
    st.data.foreach_set("uv", loop_st.ravel())
    me.uv_layers.active = uv
    for p_ in me.polygons:
        p_.use_smooth = True
    me.normals_split_custom_set_from_vertices([tuple(n) for n in mesh.N])
    la = me.attributes.new("hl", "FLOAT", "FACE")
    la.data.foreach_set("value", np.array(mesh.L, np.float32))
    gv.log(NAME, "verts", len(V), "tris", 2 * len(mesh.F))
    # ---------------------------------------------------------------- weights
    Z_ = np.array(mesh.Z)
    names = [P + "Head", P + "Neck", P + "Spine2"]
    W = np.zeros((len(V), 3))
    below = gv.ss(1.56, 1.40, Z_)                     # 0 on the skull and beside the face, 1 on the shoulders
    body_w = 0.66 * below
    W[:, 0] = 1 - body_w
    neck_share = gv.ss(1.38, 1.5, Z_)
    W[:, 1] = body_w * neck_share
    W[:, 2] = body_w * (1 - neck_share)
    gv.link_armature(o, rig)
    gv.write_weights(o, names, gv.limit_normalize(W, 4, 0.01))
    # ---------------------------------------------------------------- customisation morphs (head/chest) via binding
    Xh = gv.basis_co(o)
    bind = gv.Binding(XB, TB, Xh, 0.3)
    nshape = 0
    for n, co in gv.shape_dict(body).items():
        if not n.startswith("m_"):
            continue
        d = bind.transfer(co - XB)
        if np.abs(d).max() > 2e-4:
            gv.add_shape(o, n, Xh + d)
            nshape += 1
    gv.log(NAME, "morph shapes", nshape)
    img = paint_atlas()
    path = os.path.join(TEX, NAME + "_Color.png")
    gv.write_image(img, path)
    m = bpy.data.materials.get(NAME) or bpy.data.materials.new(NAME)
    me.materials.clear()
    me.materials.append(m)
    gv.log(NAME, "atlas", path)
    return o


# ----------------------------------------------------------------------------- strand atlas
def _strand(acc, lum, rows, x, width, a_str, bright, x_lo, x_hi, wrap=False, wsum=None):
    xi = np.floor(x).astype(int)
    for dx in (-1, 0, 1, 2):
        xx = xi + dx
        dist = np.abs(xx + 0.5 - x - 0.5)
        a = np.clip(1 - dist / (width + 0.5), 0, 1) * a_str
        if wrap:
            xx = x_lo + (xx - x_lo) % (x_hi - x_lo)
            ok = np.ones(len(xx), bool)
        else:
            ok = (xx >= x_lo) & (xx < x_hi)
        rr, cc, aa = rows[ok], xx[ok], a[ok]
        cur = acc[rr, cc]
        acc[rr, cc] = cur + aa * (1 - cur)
        lum[rr, cc] += aa * bright
        WS[rr, cc] += aa


WS = np.zeros((ATLAS, ATLAS), np.float32)


def paint_atlas():
    """Row 0 = bottom = tips (v 0), row S-1 = roots (v 1)."""
    S = ATLAS
    acc = np.zeros((S, S), np.float32)
    lum = np.zeros((S, S), np.float32)
    WS[...] = 0.0
    rng = np.random.default_rng(11)
    v = np.arange(S)
    # ---- sheet region: dense, near-opaque strands in loose groups; ragged tips
    x_lo, x_hi = 0, int(S * SHEET_U)
    groups = np.arange(x_lo + 20, x_hi, 46) + rng.uniform(-8, 8, len(np.arange(x_lo + 20, x_hi, 46)))
    for _ in range(2600):
        x0 = rng.uniform(x_lo, x_hi)
        ln = rng.uniform(0.8, 1.0)
        rows = v[int(S * (1 - ln)):]
        t = (S - 1 - rows) / S
        g = groups[np.argmin(np.abs(groups - x0))]
        pull = np.clip((t - 0.55) / 0.45, 0, 1) ** 1.6 * 0.5
        x = x0 + (g - x0) * pull + rng.uniform(1.0, 3.0) * np.sin(t * rng.uniform(6, 12) + rng.uniform(0, 6.3))
        width = rng.uniform(0.7, 1.3) * (1 - 0.5 * np.clip((t - ln * 0.85) / (ln * 0.15 + 1e-6), 0, 1))
        _strand(acc, lum, rows, x, width, rng.uniform(0.8, 1.0), rng.uniform(0.45, 1.25), x_lo, x_hi, wrap=True)
    # ---- clump strips: strands converge into 2-3 sub-clumps towards the tip (tapered, soft edges)
    sw = int(S * (1 - SHEET_U)) // CLUMP_STRIPS
    for j in range(CLUMP_STRIPS):
        lo = x_hi + j * sw + 4
        hi = x_hi + (j + 1) * sw - 4
        nsub = 2 + (j % 2)
        cents = np.linspace(lo + sw * 0.25, hi - sw * 0.25, nsub) + rng.uniform(-10, 10, nsub)
        for _ in range(520):
            x0 = lo + (hi - lo) * np.clip(rng.normal(0.5, 0.21), 0.02, 0.98)
            ln = rng.uniform(0.7, 1.0)
            rows = v[int(S * (1 - ln)):]
            t = (S - 1 - rows) / S
            c = cents[np.argmin(np.abs(cents - x0))]
            pull = np.clip((t - 0.35) / 0.65, 0, 1) ** 1.4 * 0.45
            x = x0 + (c - x0) * pull + rng.uniform(1.0, 3.5) * np.sin(t * rng.uniform(7, 14) + rng.uniform(0, 6.3))
            width = rng.uniform(0.7, 1.3) * (1 - 0.55 * np.clip((t - ln * 0.8) / (ln * 0.2 + 1e-6), 0, 1))
            _strand(acc, lum, rows, np.clip(x, lo + 1, hi - 2), width, rng.uniform(0.75, 1.0), rng.uniform(0.45, 1.25), lo, hi)
    tt = (S - 1 - v) / S                                   # 0 at the root .. 1 at the tip
    L = np.where(WS > 1e-4, lum / np.maximum(WS, 1e-4), 1.0)          # mean strand brightness (not a sum)
    root_dark = 1 - 0.3 * np.exp(-tt / 0.05)
    sheen = 1 + 0.32 * np.exp(-((tt - 0.16) / 0.05) ** 2) + 0.18 * np.exp(-((tt - 0.48) / 0.07) ** 2)
    xs = np.arange(S)
    sheen_break = 0.6 + 0.4 * np.sin(xs * 0.11)[None, :] * np.sin(xs * 0.037 + 1.3)[None, :]
    warm_tips = 1 + 0.1 * gv.ss(0.5, 1.0, tt)
    L = L * root_dark[:, None] * (1 + (sheen[:, None] - 1) * sheen_break) * warm_tips[:, None]
    base = np.array((0.6, 0.46, 0.36), np.float32)        # warm brown; the game recolours it with the hair tint
    # sun-kissed mid-lengths and lighter strand variation (the game keeps luminance variation, not hue)
    L = L * (1 + 0.12 * np.exp(-((tt - 0.55) / 0.2) ** 2))[:, None]
    col = np.clip(base[None, None, :] * L[..., None], 0, 1)
    alpha = np.clip(acc * 2.6, 0, 1)
    alpha[:, :x_hi] = np.maximum(alpha[:, :x_hi], np.where(tt[:, None] < 0.75, 0.85, 0.0))   # underlayer: no holes
    alpha *= gv.ss(0.0, 0.012, tt)[:, None]              # short root fade: the parting stays a fine line
    # clump cards fade in over their first 12 %: the crown reads as the smooth parted sheets, not stacked card ends
    alpha[:, x_hi:] *= gv.ss(0.02, 0.12, tt)[:, None]
    return np.concatenate([col, alpha[..., None]], -1)


old = bpy.data.objects.get(NAME)
if old:
    gv.remove(old)
build()
gv.save(os.path.join(gv.OUT, gv.opt(A, "--out", "giva_hair.blend")))
