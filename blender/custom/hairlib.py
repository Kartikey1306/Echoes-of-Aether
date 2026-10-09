"""Procedural hair-card library for the hero customiser.

A style is built from:
  * an inner solid volume (a shell over the scalp, thickness per region) so the scalp never shows through. Its
    texture is painted in 3-D (strands follow the style's flow field) and carries fades (stubble dots that go to
    skin), shaved line designs, a hard part and a wispy hairline (all alpha tested);
  * layered hair cards grown from roots on the scalp along a flow field, with stiffness, gravity, scalp hugging,
    collision with head/neck/shoulders/clothes, waves, helical curls, tip flicks, clumping and haircut planes;
  * special structures: gathered locks (to a ponytail / bun anchor), tails, buns and 3-strand / fishtail braids.
All cards use one material slot `Hair` and one 2048 atlas per style: 24 strand tiles (root at the top of each
tile, darker roots, lighter tips, tapered alpha) and a volume region (u 0..0.5, v 0..0.5).
Textures are neutral grey (mean albedo ~0.745) so Unity multiplies them with the hair colour.
"""
import math
import numpy as np
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
import common as C
from common import ss, nrm, nrm_rows
import gear
from gear import Part
import texbake as TB

DOWN = np.array((0.0, 0.0, -1.0))
ATLAS = 2048
VOL_RECT = (0.0, 0.0, 0.5, 0.5)


def tile_rect(k):
    """UV rect (u0, v0, u1, v1) of strand tile k (0..23)."""
    if k < 16:
        return (k / 16, 0.5, (k + 1) / 16, 1.0)
    j = k - 16
    return (0.5 + j / 16, 0.0, 0.5 + (j + 1) / 16, 0.5)


def dirv(az, el):
    az = np.asarray(az, np.float64); el = np.asarray(el, np.float64)
    return np.stack([np.sin(az) * np.cos(el), -np.cos(az) * np.cos(el), np.sin(el)], -1)


def tangents(P):
    T = np.zeros_like(P)
    T[1:-1] = P[2:] - P[:-2]
    T[0] = P[1] - P[0]
    T[-1] = P[-1] - P[-2]
    return nrm_rows(T)


def resample(P, n):
    """Resample a polyline to n points uniformly by arc length."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(seg)])
    if arc[-1] < 1e-9:
        return np.repeat(P[:1], n, 0)
    t = np.linspace(0, arc[-1], n)
    return np.stack([np.interp(t, arc, P[:, k]) for k in range(3)], 1)


def arclen(P):
    return np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


# ============================================================================= head model


class Head:
    """Head landmarks, a radial scalp map R(az, el) around the head centre (outermost head/neck surface) and
    collision against the body + outfit."""

    def __init__(self, ctx, female=False, extra_colliders=()):
        self.ctx = ctx
        L = ctx.L
        self.female = female
        self.eyeL, self.eyeR = np.array(L["LeftEye"]), np.array(L["RightEye"])
        self.eye = (self.eyeL + self.eyeR) * 0.5
        co = ctx.basis
        head = ctx.region["head"] > 0.5
        cr = co[head & (co[:, 2] > self.eye[2] + 0.01)]
        self.hc = np.array([0.0, 0.5 * (cr[:, 1].min() + cr[:, 1].max()), self.eye[2] + 0.012])
        self.top = float(cr[:, 2].max())
        self.brow_z = float(self.eye[2] + 0.024)
        self.front_y = float(cr[:, 1].min())
        self.back_y = float(cr[:, 1].max())
        self.half_w = float(np.abs(cr[:, 0]).max())
        fr = co[head & (np.abs(co[:, 2] - self.eye[2]) < 0.03) & (co[:, 1] < self.eye[1] + 0.03)]
        self.face_hw = float(np.abs(fr[:, 0]).max()) if len(fr) else 0.07
        self.neck = np.array(L["Neck"])
        self.jaw_z = float(L["Head"][2] - 0.01)
        self.shoulder_z = float(L["LeftShoulder"][2])
        B = ctx.B
        hn = ctx.region["head"] + ctx.region["neck"]
        fids = [i for i, f in enumerate(B.faces) if all(hn[v] > 0.3 for v in f)]
        self.htree = BVHTree.FromPolygons([Vector(c) for c in co], [B.faces[i] for i in fids])
        self.AZ = np.radians(np.linspace(-180, 180, 145))
        self.EL = np.radians(np.linspace(-85, 90, 71))
        R = np.full((len(self.EL), len(self.AZ)), np.nan)
        for i, e in enumerate(self.EL):
            for j, a in enumerate(self.AZ):
                d = dirv(a, e)
                o = self.hc + d * 0.4
                hit, n, _, dist = self.htree.ray_cast(Vector(o), Vector(-d), 0.4)
                if hit is not None:
                    R[i, j] = 0.4 - dist
        # fill holes by nearest valid along elevation
        for j in range(R.shape[1]):
            col = R[:, j]
            ok = ~np.isnan(col)
            if ok.any():
                R[:, j] = np.interp(np.arange(len(col)), np.where(ok)[0], col[ok])
        self.Rmap = np.nan_to_num(R, nan=0.1)
        self.colliders = list(extra_colliders)
        self.outer = ctx.outer_tree()
        self.scalp_r = float(self.R(np.array([0.0]), np.array([math.radians(60)]))[0])

    # ------------------------------------------------------------------ geometry queries
    def angles(self, P):
        d = np.asarray(P, np.float64) - self.hc
        r = np.linalg.norm(d, axis=-1)
        az = np.arctan2(d[..., 0], -d[..., 1])
        el = np.arcsin(np.clip(d[..., 2] / np.maximum(r, 1e-9), -1, 1))
        return az, el, r

    def R(self, az, el):
        az = np.asarray(az, np.float64); el = np.asarray(el, np.float64)
        fa = (az - self.AZ[0]) / (self.AZ[1] - self.AZ[0])
        fe = (np.clip(el, self.EL[0], self.EL[-1]) - self.EL[0]) / (self.EL[1] - self.EL[0])
        a0 = np.clip(np.floor(fa).astype(int), 0, len(self.AZ) - 2); e0 = np.clip(np.floor(fe).astype(int), 0, len(self.EL) - 2)
        ta = np.clip(fa - a0, 0, 1); te = np.clip(fe - e0, 0, 1)
        M = self.Rmap
        return (M[e0, a0] * (1 - ta) + M[e0, a0 + 1] * ta) * (1 - te) + (M[e0 + 1, a0] * (1 - ta) + M[e0 + 1, a0 + 1] * ta) * te

    def height(self, P):
        az, el, r = self.angles(P)
        return r - self.R(az, el)

    def surf(self, az, el, h=0.0):
        az = np.asarray(az, np.float64); el = np.asarray(el, np.float64)
        return self.hc + dirv(az, el) * (self.R(az, el) + h)[..., None]

    def radial(self, P):
        return nrm_rows(np.asarray(P) - self.hc)

    def tangent(self, P, F):
        n = self.radial(P)
        F = np.asarray(F, np.float64)
        return nrm_rows(F - n * (F * n).sum(-1, keepdims=True))

    def collide(self, q, clear, body_clear=None):
        """Keep q at least `clear` above the scalp (cranium) and `body_clear` off the body/outfit."""
        q = np.asarray(q, np.float64)
        az, el, r = self.angles(q[None])
        if el[0] > math.radians(-38) and r[0] < 0.3:
            Rr = self.R(az, el)[0]
            if r[0] - Rr < clear:
                q = self.hc + dirv(az[0], el[0]) * (Rr + clear)
        bc = clear if body_clear is None else body_clear
        hit, n, _, _ = self.outer.find_nearest(Vector(q), 0.2)
        if hit is not None:
            g = (Vector(q) - hit).dot(n)
            if g < bc:
                q = np.array(hit + n * bc)
        for tree, cl in self.colliders:
            hit, n, _, _ = tree.find_nearest(Vector(q), 0.2)
            if hit is not None:
                g = (Vector(q) - hit).dot(n)
                if g < cl:
                    q = np.array(hit + n * cl)
        return q

    # ------------------------------------------------------------------ scalp mask / hairline
    def hairline_el(self, az, kind="male"):
        """Minimum elevation (radians) of the hairline as a function of azimuth (0 front, pi back)."""
        knots = np.radians([0, 25, 50, 75, 95, 115, 140, 160, 180])  # front .. back
        if kind == "male":
            el = [33, 30, 23, 12, 3, -10, -26, -33, -36]
        elif kind == "female":
            el = [33, 31, 23, 10, 0, -14, -30, -37, -40]
        elif kind == "low":
            el = [28, 26, 19, 8, 0, -12, -28, -34, -38]
        else:
            el = kind
        return np.radians(np.interp(np.abs(az), knots, np.array(el, float)))

    def scalp(self, kind="male"):
        """(mask on body verts, az, el) of the hair-bearing scalp."""
        co = self.ctx.basis
        az, el, r = self.angles(co)
        head = self.ctx.region["head"] > 0.5
        d = co - self.hc
        ears = (np.abs(d[:, 0]) > self.half_w - 0.012) & (el < math.radians(-4)) & (np.abs(az) > math.radians(70)) & (np.abs(az) < math.radians(115))
        m = head & (el > self.hairline_el(az, kind)) & ~ears & (r < 0.2)
        return m, az, el

    def sample_roots(self, mask, n, min_d, seed=0, weight=None):
        """Area-weighted points on body faces whose vertices are all in `mask`, with a minimum spacing.
        Returns (points, normals)."""
        B = self.ctx.B
        co = self.ctx.basis
        tri = []
        for f in B.faces:
            if all(mask[v] for v in f):
                for k in range(1, len(f) - 1):
                    tri.append((f[0], f[k], f[k + 1]))
        if not tri:
            return np.zeros((0, 3)), np.zeros((0, 3))
        tri = np.array(tri)
        A = np.linalg.norm(np.cross(co[tri[:, 1]] - co[tri[:, 0]], co[tri[:, 2]] - co[tri[:, 0]]), axis=1) * 0.5
        if weight is not None:
            cen = co[tri].mean(1)
            A = A * np.maximum(weight(cen), 0)
        rng = np.random.default_rng(seed)
        m = n * 8
        pick = rng.choice(len(tri), size=m, p=A / A.sum())
        u = rng.random((m, 2))
        flip = u.sum(1) > 1
        u[flip] = 1 - u[flip]
        P = co[tri[pick, 0]] * (1 - u[:, :1] - u[:, 1:]) + co[tri[pick, 1]] * u[:, :1] + co[tri[pick, 2]] * u[:, 1:]
        Nf = nrm_rows(np.cross(co[tri[pick, 1]] - co[tri[pick, 0]], co[tri[pick, 2]] - co[tri[pick, 0]]))
        grid = {}
        out, outn = [], []
        cs = max(min_d, 1e-3)
        for p, nn in zip(P, Nf):
            key = tuple((p // cs).astype(int))
            ok = True
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for q in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                            if np.sum((p - q) ** 2) < min_d * min_d:
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if ok:
                grid.setdefault(key, []).append(p)
                out.append(p); outn.append(nn)
                if len(out) >= n:
                    break
        return np.array(out), np.array(outn)


# ============================================================================= flow helpers (vectorised)


def flow_forward(H, P, down=0.25, spread=0.0):
    F = np.zeros_like(P); F[:, 1] = -1.0; F[:, 2] = -down
    if spread:
        F[:, 0] += (P[:, 0] - H.hc[0]) * spread
    return H.tangent(P, F)


def flow_back(H, P, down=0.2):
    F = np.zeros_like(P); F[:, 1] = 1.0; F[:, 2] = -down
    return H.tangent(P, F)


def flow_down(H, P):
    F = np.zeros_like(P); F[:, 2] = -1.0
    F[:, 1] += 0.15
    return H.tangent(P, F)


def flow_from(H, P, c, down=0.0):
    """Radially away from point c (a crown whorl) along the scalp."""
    F = np.asarray(P) - c
    F[:, 2] -= down
    return H.tangent(P, F)


def flow_to(H, P, a):
    return H.tangent(P, np.asarray(a) - np.asarray(P))


def flow_part(H, P, part_x=0.0, front=-0.3, down=0.6):
    """Away from a part line x = part_x running front to back."""
    side = np.sign(P[:, 0] - part_x + 1e-6)
    F = np.stack([side, np.full(len(P), front), np.full(len(P), -down)], 1)
    return H.tangent(P, F)


def blend_flows(H, P, *pairs):
    F = np.zeros_like(np.asarray(P, np.float64))
    for w, f in pairs:
        w = np.asarray(w, np.float64)
        F += (w[:, None] if w.ndim else w) * f
    return H.tangent(P, F)


# ============================================================================= lock growth


class Lock:
    __slots__ = ("P", "layer", "tile", "width", "mode", "attrs", "w_tip", "s0")

    def __init__(self, P, layer, tile, width, mode="flat", w_tip=None):
        self.P = P; self.layer = layer; self.tile = tile; self.width = width; self.mode = mode
        self.w_tip = w_tip


def grow(H, root, n_root, L, d0, segs=16, lift=0.2, stiff=1.0, grav=0.5, off=0.006, hug=0.0, rise=0.0,
         attract=None, att_k=0.0, stop_r=0.0, clear=None, guard=None, body_clear=0.006, curve=None):
    """Integrate a lock centre line from a scalp root.
    d0: initial direction (projected on the scalp tangent plane); lift: 0 lies on the scalp, 1 straight out;
    stiff: >1 resists bending; grav: downward pull per 10 cm; hug: steering towards the target height
    off + rise * s above the scalp; attract: point the lock is steered to (att_k strength); stop_r: stop once within
    this distance of `attract`; guard(q, P) -> q (face guard etc.); curve(s) -> extra direction (3,) added per step."""
    step = L / segs
    clear = off * 0.7 if clear is None else clear
    n0 = nrm(np.asarray(n_root, np.float64))
    t0 = np.asarray(d0, np.float64) - n0 * (np.dot(d0, n0))
    t0 = nrm(t0) if np.linalg.norm(t0) > 1e-6 else nrm(np.cross(n0, (1, 0, 0)))
    d = nrm(t0 * (1 - lift) + n0 * lift)
    p = np.asarray(root, np.float64) + n0 * off
    P = [p]
    for i in range(segs):
        s = (i + 0.5) / segs
        dn = d * stiff
        dn = dn + DOWN * grav * step / 0.1
        if hug > 0:
            az, el, r = H.angles(p[None])
            if el[0] > math.radians(-40):
                h = r[0] - H.R(az, el)[0]
                tgt = off + rise * s
                rad = nrm(p - H.hc)
                dn = dn - rad * hug * np.clip((h - tgt) / 0.01, -1.5, 1.5) * 0.35
        if attract is not None:
            a = np.asarray(attract) - p
            dist = np.linalg.norm(a)
            if stop_r and dist < stop_r:
                break
            dn = dn + nrm(a) * att_k
        if curve is not None:
            dn = dn + curve(s, p, d)
        d = nrm(dn)
        q = p + d * step
        q = H.collide(q, clear, body_clear)
        if guard is not None:
            q = guard(q, p)
            if q is None:
                break
        if np.linalg.norm(q - p) < 1e-6:
            break
        d = nrm(q - p)
        P.append(q)
        p = q
    return np.array(P)


def frame(H, P, ref=None):
    """Per-point (T, S, Nn): tangent, side (card width direction) and card normal (away from the head axis)."""
    T = tangents(P)
    if ref is None:
        axis = np.stack([np.full(len(P), H.hc[0]), np.full(len(P), H.hc[1] + 0.01), np.minimum(P[:, 2], H.hc[2])], 1)
        Nout = nrm_rows(P - axis)
    else:
        Nout = nrm_rows(np.broadcast_to(ref, P.shape).copy())
    S = np.cross(T, Nout)
    bad = np.linalg.norm(S, axis=1) < 0.15
    if bad.any():
        alt = np.cross(T[bad], np.array((1.0, 0, 0)))
        alt2 = np.cross(T[bad], np.array((0, 1.0, 0)))
        use2 = np.linalg.norm(alt, axis=1) < 0.2
        alt[use2] = alt2[use2]
        S[bad] = alt
    S = nrm_rows(S)
    Nn = nrm_rows(np.cross(S, T))
    return T, S, Nn


def shape(H, P, rng, wave=None, curl=None, flick=0.0, frizz=0.0, clear=0.004, body_clear=0.005, ramp=(0.08, 0.4)):
    """Wave (amp, wavelength), helical curl (radius, pitch) and tip flick (outward metres) as offsets in the lock
    frame; re-collided afterwards. Returns (P2, side_override or None, Nlock)."""
    T, S, Nn = frame(H, P)
    arc = arclen(P)
    sN = arc / max(arc[-1], 1e-6)
    off = np.zeros_like(P)
    side = None
    lock_n = Nn
    k = ss(ramp[0], ramp[1], sN)
    if wave:
        amp, lam = wave
        ph = rng.uniform(0, 2 * math.pi)
        th = 2 * math.pi * arc / lam + ph
        off += S * (amp * k * np.sin(th))[:, None] + Nn * (amp * 0.45 * k * np.cos(th))[:, None]
    if curl:
        rad, pitch = curl
        ph = rng.uniform(0, 2 * math.pi)
        th = 2 * math.pi * arc / pitch + ph
        radial = S * np.cos(th)[:, None] + Nn * np.sin(th)[:, None]
        off += radial * (rad * k)[:, None]
        side = T
        lock_n = radial
    if flick:
        off += Nn * (flick * ss(0.6, 1.0, sN) ** 2)[:, None]
    if frizz:
        off += rng.normal(0, frizz, P.shape) * (sN ** 1.5)[:, None]
    P2 = P + off
    P2 = np.array([P2[0]] + [H.collide(q, clear, body_clear) for q in P2[1:]])
    return P2, side, lock_n


def cut(P, below):
    """Truncate a lock where predicate below(points) first becomes True (linear interpolation of the crossing)."""
    b = below(P)
    if not b.any():
        return P
    i = int(np.argmax(b))
    if i == 0:
        return P[:1]
    # bisect between i-1 and i
    a, c = P[i - 1], P[i]
    for _ in range(12):
        m = (a + c) * 0.5
        if below(m[None])[0]:
            c = m
        else:
            a = m
    return np.vstack([P[:i], a[None]])


def clump(locks, frac=0.35, strength=0.6, seed=0):
    """Pull lock tips together in clumps (piecey texture)."""
    if len(locks) < 4:
        return
    rng = np.random.default_rng(seed)
    tips = np.array([lk.P[-1] for lk in locks])
    k = max(2, int(len(locks) * frac))
    cen = tips[rng.choice(len(tips), k, replace=False)]
    for _ in range(6):
        lab = np.argmin(((tips[:, None] - cen[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                cen[j] = tips[lab == j].mean(0)
    lab = np.argmin(((tips[:, None] - cen[None]) ** 2).sum(-1), 1)
    for lk, j in zip(locks, lab):
        arc = arclen(lk.P)
        s = arc / max(arc[-1], 1e-6)
        dlt = (cen[j] - lk.P[-1])
        if np.linalg.norm(dlt) > 0.03:
            continue
        lk.P = lk.P + dlt[None] * (strength * s ** 2)[:, None]


# ============================================================================= card meshes


def card_strip(part, P, side, width, tile, layer, normals, vrange=None):
    """Ribbon along P (root first) spanning +-side*width/2. UV: across the tile's u range, v from tile top (root)
    down to the bottom (tip). normals: per point card normal (for shading)."""
    n = len(P)
    if n < 2:
        return
    u0, v0, u1, v1 = tile_rect(tile)
    pad = (u1 - u0) * 0.03
    u0 += pad; u1 -= pad
    vt, vb = (v1 - 0.004, v0 + 0.004) if vrange is None else vrange
    w = np.broadcast_to(np.asarray(width, np.float64), (n,))
    verts = np.empty((2 * n, 3))
    verts[0::2] = P - side * (w * 0.5)[:, None]
    verts[1::2] = P + side * (w * 0.5)[:, None]
    arc = arclen(P)
    s = arc / max(arc[-1], 1e-9)
    faces, uvs = [], []
    for i in range(n - 1):
        a = 2 * i
        f = [a, a + 2, a + 3, a + 1]
        va = vt + (vb - vt) * s[i]
        vb_ = vt + (vb - vt) * s[i + 1]
        uv = [(u0, va), (u0, vb_), (u1, vb_), (u1, va)]
        fnrm = np.cross(verts[a + 2] - verts[a], verts[a + 1] - verts[a])
        if np.dot(fnrm, normals[i] + normals[i + 1]) < 0:      # geometric normal must face outwards (two-sided shading)
            f = f[::-1]; uv = uv[::-1]
        faces.append(f); uvs.append(uv)
    ln = np.repeat(normals, 2, axis=0)
    part.add(verts, faces, "Hair", uvs, {"lnx": ln[:, 0], "lny": ln[:, 1], "lnz": ln[:, 2], "layer": np.full(2 * n, float(layer)),
                                          "hairvol": np.zeros(2 * n)})


def build_cards(H, locks, name, rng):
    part = Part(name)
    for lk in locks:
        P = lk.P
        if len(P) < 3:
            continue
        arc = arclen(P)
        if arc[-1] < 0.006:
            continue
        T, S, Nn = frame(H, P)
        side = S
        nrmls = Nn
        if lk.mode == "ringlet" and lk.attrs is not None:
            side, nrmls = lk.attrs
        s = arc / arc[-1]
        w_tip = lk.w_tip if lk.w_tip is not None else lk.width * 0.45
        w = lk.width + (w_tip - lk.width) * s ** 1.2
        if lk.mode == "ringlet":
            card_strip(part, P, side, w, lk.tile, lk.layer, nrmls)
        elif lk.mode == "cross":
            card_strip(part, P, S, w, lk.tile, lk.layer, Nn)
            card_strip(part, P, Nn, w * 0.8, lk.tile, lk.layer, -S if rng.random() < 0.5 else S)
        else:
            card_strip(part, P, side, w, lk.tile, lk.layer, nrmls)
    if not part.F:
        return None
    return part.build(mat_order=["Hair"], max_edge=None)


def tube_lobes(part, P, radius, sides, tile, layer, lobe_len, normals_out=True, twist=0.0):
    """Closed tube along P with radius(s) array; UV v repeats per lobe (one tile height per `lobe_len`)."""
    n = len(P)
    T = tangents(P)
    ref = np.array((0, 0, 1.0)) if abs(T[0][2]) < 0.9 else np.array((1.0, 0, 0))
    A = nrm_rows(np.cross(T, ref))
    # parallel transport
    for i in range(1, n):
        a = A[i - 1] - T[i] * np.dot(A[i - 1], T[i])
        A[i] = nrm(a) if np.linalg.norm(a) > 1e-6 else A[i - 1]
    Bv = np.cross(T, A)
    u0, v0, u1, v1 = tile_rect(tile)
    arc = arclen(P)
    verts, faces, uvs, nr = [], [], [], []
    for i in range(n):
        for k in range(sides):
            th = 2 * math.pi * k / sides + twist * arc[i]
            dvec = A[i] * math.cos(th) + Bv[i] * math.sin(th)
            verts.append(P[i] + dvec * radius[i])
            nr.append(dvec)
    for i in range(n - 1):
        for k in range(sides):
            a = i * sides + k
            b = i * sides + (k + 1) % sides
            c = (i + 1) * sides + (k + 1) % sides
            d = (i + 1) * sides + k
            f = [a, b, c, d]
            fnrm = np.cross(verts[b] - verts[a], verts[d] - verts[a])
            flip = np.dot(fnrm, nr[a] + nr[c]) < 0
            faces.append(f[::-1] if flip else f)
            fa = (arc[i] / lobe_len) % 1.0
            fb = fa + (arc[i + 1] - arc[i]) / lobe_len
            ua = u0 + (u1 - u0) * (0.08 + 0.84 * k / sides)
            ub = u0 + (u1 - u0) * (0.08 + 0.84 * (k + 1) / sides)
            va = v1 - (v1 - v0) * (0.02 + 0.96 * min(fa, 1.0))
            vb = v1 - (v1 - v0) * (0.02 + 0.96 * min(fb, 1.0))
            uvq = [(ua, va), (ub, va), (ub, vb), (ua, vb)]
            uvs.append(uvq[::-1] if flip else uvq)
    nr = np.array(nr)
    part.add(np.array(verts), faces, "Hair", uvs, {"lnx": nr[:, 0], "lny": nr[:, 1], "lnz": nr[:, 2], "layer": np.full(len(verts), float(layer)),
                                                   "hairvol": np.zeros(len(verts))})


# ============================================================================= structures


def braid3(H, part, path, width, tile, layer, rng, flat=0.55, period=None, sides=6, fuzz=None, taper=0.3):
    """Classic 3-strand braid along `path` (points, root first). Each strand is a lobed tube weaving across
    the braid: lateral sin(w t + 2 pi i/3), depth sin(2 w t + 4 pi i/3)."""
    P = resample(path, max(24, int(arclen(path)[-1] / 0.004)))
    T, S, Nn = frame(H, P)
    arc = arclen(P)
    Ltot = arc[-1]
    period = period or width * 2.2
    s = arc / Ltot
    wid = width * (1 - taper * s)
    strands = []
    for i in range(3):
        ph = 2 * math.pi * i / 3
        th = 2 * math.pi * arc / period + ph
        lat = np.sin(th) * 0.5 * wid
        dep = np.sin(2 * th) * 0.22 * wid * flat
        Q = P + S * lat[:, None] + Nn * dep[:, None]
        r = wid * 0.32 * (0.82 + 0.18 * np.cos(2 * th))
        tube_lobes(part, Q, r, sides, tile, layer, period / 2)
        strands.append(Q)
    return P, wid


def fishtail(H, part, path, width, tile, layer, rng, period=None, taper=0.35):
    """Fishtail braid: herringbone of small flattened lobes alternating left/right along the path."""
    P = resample(path, max(30, int(arclen(path)[-1] / 0.003)))
    T, S, Nn = frame(H, P)
    arc = arclen(P)
    Ltot = arc[-1]
    period = period or width * 0.42
    n = int(Ltot / (period * 0.5))
    for j in range(n):
        t = (j + 0.5) * period * 0.5
        i = int(np.searchsorted(arc, t))
        i = min(i, len(P) - 2)
        s = t / Ltot
        w = width * (1 - taper * s)
        side = 1 if j % 2 == 0 else -1
        # lobe: from the outer edge on `side` diagonally down to the centre
        c = P[i]
        a = c + S[i] * side * w * 0.48 - T[i] * period * 0.15
        b = c - S[i] * side * w * 0.05 + T[i] * period * 0.55
        Q = np.array([a + (b - a) * u for u in np.linspace(0, 1, 6)])
        Q += Nn[i] * (np.sin(np.linspace(0, math.pi, 6)) * w * 0.12)[:, None]
        rr = w * 0.17 * np.sin(np.linspace(0.25, math.pi - 0.25, 6))
        tube_lobes(part, Q, rr, 6, tile, layer, np.linalg.norm(b - a) * 1.02)
    return P


def bun(H, part, center, axis, radius, tile_range, layer, rng, wraps=3.2, messy=0.0, height=None, cards=70):
    """Coiled bun: a solid core (sphere) + coils of cards wrapped around `axis` at `center`."""
    axis = nrm(axis)
    ref = np.array((0, 0, 1.0)) if abs(axis[2]) < 0.9 else np.array((1.0, 0, 0))
    A = nrm(np.cross(axis, ref)); Bv = np.cross(axis, A)
    height = height or radius * 1.2
    # core
    nlat, nlon = 9, 16
    verts, faces, uvs, nr = [], [], [], []
    u0, v0, u1, v1 = tile_rect(tile_range[0])
    for i in range(nlat + 1):
        th = math.pi * i / nlat
        for j in range(nlon):
            ph = 2 * math.pi * j / nlon
            dvec = axis * math.cos(th) * 0.8 + (A * math.cos(ph) + Bv * math.sin(ph)) * math.sin(th)
            verts.append(center + dvec * radius * 0.86)
            nr.append(nrm(dvec))
    vv = np.array(verts)
    for i in range(nlat):
        for j in range(nlon):
            a = i * nlon + j; b = i * nlon + (j + 1) % nlon
            c = (i + 1) * nlon + (j + 1) % nlon; d = (i + 1) * nlon + j
            fl = np.dot(np.cross(vv[b] - vv[a], vv[d] - vv[a]) + np.cross(vv[c] - vv[b], vv[a] - vv[b]), vv[a] + vv[c] - 2 * center) < 0
            faces.append([d, c, b, a] if fl else [a, b, c, d])
            uvq = [(u0 + (u1 - u0) * (j / nlon), v1 - (v1 - v0) * (0.1 + 0.8 * i / nlat)),
                   (u0 + (u1 - u0) * ((j + 1) / nlon), v1 - (v1 - v0) * (0.1 + 0.8 * i / nlat)),
                   (u0 + (u1 - u0) * ((j + 1) / nlon), v1 - (v1 - v0) * (0.1 + 0.8 * (i + 1) / nlat)),
                   (u0 + (u1 - u0) * (j / nlon), v1 - (v1 - v0) * (0.1 + 0.8 * (i + 1) / nlat))]
            uvs.append(uvq[::-1] if fl else uvq)
    nr = np.array(nr)
    part.add(np.array(verts), faces, "Hair", uvs, {"lnx": nr[:, 0], "lny": nr[:, 1], "lnz": nr[:, 2], "layer": np.full(len(verts), float(layer)),
                                                   "hairvol": np.ones(len(verts))})
    # coil cards: each card follows a helix-like wrap around the axis over the bun surface
    for k in range(cards):
        t0 = rng.uniform(0, 1)
        ph0 = rng.uniform(0, 2 * math.pi)
        npt = 22
        ang = ph0 + np.linspace(0, 2 * math.pi * rng.uniform(0.55, 1.1), npt)
        hgt = (t0 - 0.5) * 2  # -1..1 along axis
        lat = math.acos(np.clip(hgt * 0.85, -0.95, 0.95))
        lat_path = lat + np.linspace(0, rng.uniform(-0.6, 0.6), npt)
        rad = radius * (1.0 + rng.uniform(0.0, 0.12) + messy * rng.uniform(0, 0.35) * np.sin(np.linspace(0, math.pi, npt)))
        Pc = np.array([center + (axis * math.cos(lp) * 0.8 + (A * math.cos(a_) + Bv * math.sin(a_)) * math.sin(lp)) * r_
                       for a_, lp, r_ in zip(ang, lat_path, rad)])
        if messy:
            Pc += rng.normal(0, messy * 0.002, Pc.shape) * np.linspace(0, 1, npt)[:, None]
        nrm_ = nrm_rows(Pc - center)
        T = tangents(Pc)
        S = nrm_rows(np.cross(T, nrm_))
        w = radius * rng.uniform(0.55, 0.8) * np.sin(np.linspace(0.35, math.pi - 0.35, npt))
        tile = int(rng.integers(tile_range[0], tile_range[1] + 1))
        card_strip(part, Pc, S, w, tile, layer + 1, nrm_)


# ============================================================================= volume shell


def volume_shell(H, ctx, name, mask, thick_fn, subdiv=1, smooth=6):
    """Solid inner volume over the scalp faces in `mask`; thick_fn(az, el) -> metres. UVs: MakeHuman head UVs
    normalised into VOL_RECT (painted in 3-D later)."""
    def off(P, N):
        az, el, r = H.angles(P)
        return np.maximum(thick_fn(az, el), 0.0012)
    vol = gear.shell(ctx, name, mask, off, mats=("Hair",), smooth=smooth, subdiv=subdiv, rim=0.0, stack=False, cover=False,
                     bsmooth=14, min_clear=0.0011)
    me = vol.data
    uv = me.uv_layers.active
    a = np.empty(len(me.loops) * 2); uv.data.foreach_get("uv", a); a = a.reshape(-1, 2)
    lo, hi = a.min(0), a.max(0)
    sc = 0.96 / np.maximum(hi - lo, 1e-6)
    u0, v0, u1, v1 = VOL_RECT
    a = (a - lo) * sc[None] + 0.02
    a[:, 0] = u0 + a[:, 0] * (u1 - u0)
    a[:, 1] = v0 + a[:, 1] * (v1 - v0)
    uv.data.foreach_set("uv", a.ravel())
    nv = len(me.vertices)
    for k in ("lnx", "lny", "lnz", "layer"):
        gear.set_attr(vol, k, np.zeros(nv))
    gear.set_attr(vol, "hairvol", np.ones(nv))
    return vol


# ============================================================================= textures


def draw_strands(W, H_, n, rng, curl=0.0, wave=0.0, width=(0.7, 1.5), taper=0.45, root_dark=0.4, sheen=(0.55, 0.18),
                 frizz=0.0, tipfade=(0.5, 1.0), converge=0.0, full=False, clumps=(4, 8), spread=0.30):
    """n anti-aliased strands along v (row 0 = tip, last row = root) in a W x H tile, grouped in sub-clumps
    (gaussian around clump centres, converging towards the tip) so the card edges are soft and the tips piecey.
    Returns lum (H, W) and alpha (H, W)."""
    lum = np.zeros((H_, W), np.float32)
    alpha = np.zeros((H_, W), np.float32)
    v = (np.arange(H_) + 0.5) / H_            # 0 tip .. 1 root (row 0 is the bottom of the tile)
    xs = np.arange(W)[None, :].astype(np.float32)
    nc = int(rng.integers(clumps[0], clumps[1] + 1))
    centres = np.sort(rng.uniform(0.18, 0.82, nc)) * W
    csig = W * spread / math.sqrt(nc)
    cph = rng.uniform(0, 2 * math.pi, nc)
    cval = rng.uniform(0.62, 1.1, nc)          # per-clump value: light/dark streaks that survive mip-mapping
    order = rng.permutation(n)
    for si in range(n):
        c = int(order[si] % nc)
        x0 = centres[c] + rng.normal(0, csig)
        x0 = float(np.clip(x0, 2, W - 3))
        ln = 1.0 if full else rng.uniform(*tipfade) * (1.0 - 0.35 * min(1.0, abs(x0 - W / 2) / (W / 2)) ** 2)
        ph = rng.uniform(0, 2 * math.pi)
        amp = W * (0.006 + curl * rng.uniform(0.05, 0.1) + wave * 0.025)
        freq = 1.2 + curl * rng.uniform(6, 10) + wave * rng.uniform(0.8, 1.6)
        cphase = cph[c] if curl > 0 else ph
        cx = x0 + amp * np.sin(v * freq * 2 * math.pi + cphase + rng.normal(0, 0.25))
        if converge:
            cx = cx + (centres[c] - cx) * converge * (1 - v) ** 1.3
        if frizz:
            cx = cx + np.cumsum(rng.normal(0, frizz, H_)) * 0.04 * (1 - v)
        w = rng.uniform(*width) * (1 - taper * (1 - v))
        tip = ss(1 - ln, 1 - ln + 0.08, v) if not full else np.ones_like(v)
        a = np.clip(0.5 + (w[:, None] * 0.5 - np.abs(xs - cx[:, None])), 0, 1) * tip[:, None]
        b = cval[c] * rng.uniform(0.72, 1.0)
        l = b * (1 - root_dark * ss(0.65, 1.0, v)) * (0.85 + 0.25 * (1 - v)) * (1 + sheen[1] * np.exp(-((v - sheen[0]) / 0.08) ** 2) * 1.6)
        lum = lum * (1 - a) + l[:, None] * a
        alpha = alpha + a * (1 - alpha)
    lum = np.where(alpha > 1e-3, lum / np.maximum(alpha, 1e-3), 0)
    return lum, np.clip(alpha * 1.15, 0, 1)


TILE_FLAVORS = {
    # n strands, curl, wave, width (px at 2048), taper, frizz, converge, core density near the root
    "straight": dict(n=260, curl=0.0, wave=0.0, width=(0.8, 1.5), taper=0.45, frizz=0.0, converge=0.25, core=0.45),
    "sleek":    dict(n=320, curl=0.0, wave=0.0, width=(0.7, 1.3), taper=0.35, frizz=0.0, converge=0.15, core=0.6, sheen=0.3, spread=0.36),
    "wavy":     dict(n=260, curl=0.0, wave=0.6, width=(0.8, 1.5), taper=0.45, frizz=0.0, converge=0.25, core=0.45),
    "spiky":    dict(n=220, curl=0.0, wave=0.0, width=(0.9, 1.8), taper=0.7, frizz=0.0, converge=0.6, core=0.35),
    "messy":    dict(n=240, curl=0.08, wave=0.3, width=(0.8, 1.6), taper=0.55, frizz=0.5, converge=0.35, core=0.35),
    "curly":    dict(n=230, curl=0.5, wave=0.0, width=(0.9, 1.7), taper=0.45, frizz=0.25, converge=0.15, core=0.45),
    "coily":    dict(n=240, curl=1.0, wave=0.0, width=(1.0, 1.9), taper=0.35, frizz=0.7, converge=0.1, core=0.5),
    "wisp":     dict(n=60, curl=0.0, wave=0.25, width=(0.6, 1.1), taper=0.6, frizz=0.2, converge=0.3, core=0.0, clumps=(2, 3)),
    "sheet":    dict(n=420, curl=0.0, wave=0.15, width=(0.8, 1.5), taper=0.4, frizz=0.0, converge=0.12, core=0.8, spread=0.55, clumps=(6, 10)),
    "sheetwave": dict(n=420, curl=0.0, wave=0.6, width=(0.8, 1.5), taper=0.4, frizz=0.0, converge=0.12, core=0.8, spread=0.55, clumps=(6, 10)),
    "sheetcurl": dict(n=420, curl=0.45, wave=0.0, width=(0.9, 1.6), taper=0.4, frizz=0.2, converge=0.1, core=0.8, spread=0.55, clumps=(6, 10)),
    "braid":    dict(n=300, curl=0.0, wave=0.1, width=(0.9, 1.7), taper=0.0, frizz=0.0, converge=0.0, core=1.0, full=True, spread=0.6),
}


def paint_tiles(img, flavors, rng, lum_mul=None):
    """Paint 24 strand tiles into img (ATLAS x ATLAS x 4, row 0 = v 0). flavors: list of 24 flavor names."""
    S = img.shape[0]
    tw = S // 16
    th = S // 2
    for k, fl in enumerate(flavors):
        if fl is None:
            continue
        p = TILE_FLAVORS[fl]
        lum, al = draw_strands(tw, th - 8, p["n"], rng, curl=p["curl"], wave=p["wave"], width=tuple(w * S / 2048 for w in p["width"]),
                               taper=p["taper"], frizz=p["frizz"], converge=p["converge"], full=p.get("full", False),
                               sheen=(0.55, p.get("sheen", 0.18)), clumps=p.get("clumps", (4, 8)), spread=p.get("spread", 0.3))
        if p["core"] > 0:
            xs = np.abs(np.arange(tw) - (tw - 1) / 2) / (tw / 2)
            v = (np.arange(th - 8) + 0.5) / (th - 8)
            core = (1 - ss(0.25, 0.7, xs))[None, :] * (ss(0.35, 0.85, v)[:, None] if not p.get("full") else 1.0)
            al = np.maximum(al, core * p["core"])
            lum = np.where(al > 0.02, np.where(lum > 0, lum, 0.25), 0.25)
        m = 1.0 if lum_mul is None else lum_mul[k]
        u0, v0, u1, v1 = tile_rect(k)
        x0 = int(round(u0 * S)); y0 = int(round(v0 * S)) + 4
        img[y0:y0 + th - 8, x0:x0 + tw, 0] = lum * m
        img[y0:y0 + th - 8, x0:x0 + tw, 3] = al
    return img


def worley2(P, freq, seed=0.0):
    Q = P * freq
    i = np.floor(Q)
    best = np.full(len(Q), 9.0); fp_best = np.zeros_like(Q)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                g = i + np.array((dx, dy, dz))
                fp = g + np.stack([TB.hash3(g, seed), TB.hash3(g, seed + 1.3), TB.hash3(g, seed + 2.7)], -1)
                d = np.linalg.norm(Q - fp, axis=1)
                m = d < best
                best = np.where(m, d, best)
                fp_best = np.where(m[:, None], fp, fp_best)
    return best, fp_best / freq


def paint_volume(H, vol, img, style, rng):
    """3-D painted volume texture in VOL_RECT: strands along the style flow, curly mats, fades, designs, part
    line and wispy hairline. style: dict with flow(P)->F, texture kind, fade(az, el)->density, design(az, el)->cut,
    part(az, el)->cut, hairline kind."""
    S = img.shape[0]
    T = TB.raster([vol], "Hair", S, attrs=())
    idx = np.where(T.cov)[0]
    P = T.P[idx].astype(np.float64)
    N = T.N[idx].astype(np.float64)
    az, el, r = H.angles(P)
    F = style["flow"](P)
    F = nrm_rows(F - N * (F * N).sum(1, keepdims=True))
    Bv = np.cross(N, F)
    kind = style.get("vol_tex", "straight")
    across = (P * Bv).sum(1) + 0.0012 * TB.fbm3(P, 70.0, 2, 1.0)
    along = (P * F).sum(1)
    if kind in ("curly", "coily"):
        f1, fp = worley2(P, 75.0 if kind == "curly" else 110.0, 2.0)
        v = P - fp
        v = v - N * (v * N).sum(1, keepdims=True)
        rr = np.linalg.norm(v, axis=1)
        t1 = nrm_rows(np.cross(N, np.array((0.0, 0.0, 1.0))))
        t2 = np.cross(N, t1)
        ang = np.arctan2((v * t2).sum(1), (v * t1).sum(1))
        spiral = 0.5 + 0.5 * np.cos(2 * math.pi * rr / (0.0024 if kind == "curly" else 0.0019) + ang * 2 + TB.hash3(fp, 5.0) * 6.28)
        dome = np.clip(1 - f1 / 0.8, 0, 1)
        st = (0.35 + 0.65 * spiral) * (0.45 + 0.55 * dome)
    else:
        st = np.zeros(len(P))
        for k, (cw, cl, sd) in enumerate(((0.00095, 0.006, 1.0), (0.0008, 0.0045, 2.0), (0.0011, 0.008, 3.0))):
            ac = across + 0.0004 * k + 0.0008 * TB.vnoise3(P, 60.0, sd)
            ia = np.floor(ac / cw)
            al_ = along + TB.hash2(ia, 0.0, sd) * cl
            ja = np.floor(al_ / cl)
            lx = ac / cw - ia - 0.5
            ly = al_ / cl - ja
            h = TB.hash2(ia, ja, sd + 0.5)
            stroke = (np.abs(lx) < 0.36) * (ly < 0.55 + 0.45 * h) * (1 - 0.6 * ly)
            st = np.maximum(st, stroke * (0.45 + 0.55 * TB.hash2(ia, ja, sd + 1.7)))
        clumpv = 0.5 + 0.5 * TB.fbm3(P, 45.0, 2, 3.0)
        st = 0.1 + 0.75 * st + 0.3 * clumpv
    lum = (0.2 + 0.75 * st) * style.get("vol_lum", 0.82)
    alpha = np.ones(len(idx), np.float32)
    # fades: density 0 (skin) .. 1 (full hair); stubble dots
    if style.get("fade") is not None:
        dens = np.clip(style["fade"](az, el, P), 0, 1)
        # coverage-proportional stubble: jittered dots whose area fraction equals the density (reads as a smooth
        # fade under TAA / alpha clip), blending into the strand texture where the hair is full
        cell = 0.0011
        q = np.floor(P / cell)
        hsh = TB.hash3(q, 7.0)
        jit = np.stack([TB.hash3(q, 1.1), TB.hash3(q, 2.3), TB.hash3(q, 3.7)], 1) - 0.5
        sub = P / cell - q - 0.5 - jit * 0.35
        rad = np.sqrt(np.clip(dens, 0, 1) * 0.9 / math.pi) * 1.25
        dot = (np.linalg.norm(sub, axis=1) < rad).astype(np.float32)
        short = dens < 0.999
        tr = ss(0.8, 0.97, dens)  # where dense enough, use the strand texture
        alpha = np.where(short, np.maximum(dot, tr), 1.0).astype(np.float32)
        lum = np.where(short, lum * tr + (1 - tr) * (0.22 + 0.2 * hsh), lum)
    # shaved designs (alpha 0 = skin); parting lines only darken the roots (a skin stripe reads as a bald line in-game)
    for key in ("design", "part"):
        fn = style.get(key)
        if fn is not None:
            c = fn(az, el, P)
            if key == "design":
                alpha = np.where(c > 0.5, 0.0, alpha).astype(np.float32)
                lum = np.where((c > 0.2) & (c <= 0.5), lum * 0.6, lum)
            else:
                lum = np.where(c > 0.5, lum * 0.55, np.where(c > 0.2, lum * 0.75, lum))
    # wispy hairline: break into strands within ~4 deg of the hairline
    hl = style.get("hairline", "male")
    el_min = H.hairline_el(az, hl)
    edge = (el - el_min) / math.radians(style.get("hairline_soft", 4.0))
    near = edge < 1.0
    wisp = st > 0.3 + 0.55 * (1 - np.clip(edge, 0, 1))
    alpha = np.where(near & (alpha > 0.5), wisp.astype(np.float32), alpha).astype(np.float32)
    out = np.zeros((S * S, 4), np.float32)
    out[idx, 0] = lum
    out[idx, 3] = alpha
    out = out.reshape(S, S, 4)
    cov = T.cov.reshape(S, S)
    # only write the volume rect
    u0, v0, u1, v1 = VOL_RECT
    ys, ye, xs, xe = int(v0 * S), int(v1 * S), int(u0 * S), int(u1 * S)
    sub = out[ys:ye, xs:xe]
    csub = cov[ys:ye, xs:xe]
    a_keep = sub[..., 3].copy()
    sub = TB.dilate(sub, csub, 6)
    sub[..., 3] = np.where(csub, a_keep, sub[..., 3])
    img[ys:ye, xs:xe] = sub
    return img


def finish_atlas(img, base_rgb=(1.0, 1.0, 1.0), target_mean=0.745):
    """Neutral grey RGBA: luminance normalised so the mean over alpha > 0.5 is ~target_mean."""
    lum = img[..., 0]
    a = img[..., 3]
    m = lum[a > 0.5].mean() if (a > 0.5).any() else 0.5
    lum = np.clip(lum / max(m, 1e-3) * target_mean, 0, 1)
    out = np.zeros_like(img)
    for c in range(3):
        out[..., c] = lum * base_rgb[c]
    out[..., 3] = a
    # transparent texels: flatten colour (smaller PNG) but keep a dilated border for mip filtering
    out[..., :3] = bleed(out[..., :3], a)
    return np.clip(out, 0, 1)


def bleed(rgb, a, thr=0.3, iters=24):
    """Colour bleed into transparent texels (so alpha-clip edges and mips never pick up black): dilate the colour
    of texels with alpha > thr outwards, then fill whatever is left with the mean hair value."""
    cov = a > thr
    out = TB.dilate(rgb, cov, iters)
    grown = TB.dilate(cov.astype(np.float32)[..., None], cov, iters)[..., 0] > 0.5
    mean = rgb[cov].mean(0) if cov.any() else np.full(3, 0.5)
    out[~grown] = mean
    # keep the original colour where the texel is meaningfully opaque
    keep = a > 0.6
    out[keep] = rgb[keep]
    return out


# ============================================================================= normals / finalize


def card_normals(obj, hc, card_mix=0.45, squash=(1.0, 1.0, 1.25)):
    """Card vertices get normals pointing away from the head volume (ellipsoid around hc) mixed with their own
    lock normal; the volume keeps smooth normals. Stored as custom split normals."""
    me = obj.data
    me.update()
    co = gear.get_co(obj)
    vn = gear.vnormals(obj)
    hv = gear.attr(obj, "hairvol")
    d = (co - hc) / np.array(squash)
    sph = nrm_rows(d)
    ln = np.stack([gear.attr(obj, "lnx"), gear.attr(obj, "lny"), gear.attr(obj, "lnz")], 1)
    has = np.linalg.norm(ln, axis=1) > 0.5
    own = np.where(has[:, None], ln, vn)
    sgn = np.sign((own * sph).sum(1, keepdims=True)); sgn[sgn == 0] = 1
    own = own * sgn
    n = np.where(hv[:, None] > 0.5, vn, sph * (1 - card_mix) + own * card_mix)
    n = nrm_rows(n)
    me.normals_split_custom_set_from_vertices([tuple(v) for v in n])
    return n


def hair_weights(obj, H, mode="rigid"):
    """rigid: 100 % Head. skinned: Head above the jaw blending to Neck and Spine2 towards the shoulders, so locks
    below the jaw follow the torso instead of swinging through the shoulders."""
    co = gear.get_co(obj)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    if mode == "rigid":
        vg = obj.vertex_groups.new(name="mixamorig:Head")
        vg.add(list(range(len(co))), 1.0, "REPLACE")
        return
    zj = H.jaw_z
    zs = H.shoulder_z + 0.02
    t = np.clip((zj - co[:, 2]) / max(zj - zs, 1e-3), 0, 1.6)
    # hair behind the head that is still above the jaw stays on the head
    wh = np.clip(1 - t * 0.8, 0.0, 1.0)
    ws = np.clip((t - 0.55) * 1.1, 0, 0.75)
    wn = np.clip(1 - wh - ws, 0, 1)
    for nm, w in (("Head", wh), ("Neck", wn), ("Spine2", ws)):
        vg = obj.vertex_groups.new(name="mixamorig:" + nm)
        ids = np.where(w > 0.01)[0]
        for i in ids:
            vg.add([int(i)], float(w[i]), "REPLACE")


# ============================================================================= hair sheets (long hair mass)


def sheet_strips(part, guides, tile_lo, tile_hi, layer, normals, cols_per_tile=3, max_gap=0.06, rng=None, vtop=None):
    """Quad strips between consecutive guide paths (all resampled to the same point count). Adjacent columns form
    one continuous curtain of hair; UVs: each run of `cols_per_tile` columns spans one strand tile across u, root to tip
    along v. Quads where neighbouring guides are further apart than max_gap are skipped (openings)."""
    ntile = tile_hi - tile_lo + 1
    for i in range(len(guides) - 1):
        A, B = guides[i], guides[i + 1]
        if A is None or B is None:
            continue
        n = min(len(A), len(B))
        k = tile_lo + ((i // cols_per_tile) + (0 if rng is None else int(rng.integers(0, 3)))) % ntile
        u0, v0, u1, v1 = tile_rect(k)
        pad = (u1 - u0) * 0.02
        j = i % cols_per_tile
        ua = u0 + pad + (u1 - u0 - 2 * pad) * j / cols_per_tile
        ub = u0 + pad + (u1 - u0 - 2 * pad) * (j + 1) / cols_per_tile
        vt, vb = v1 - 0.004, v0 + 0.004
        verts, faces, uvs = [], [], []
        arcA = arclen(A[:n]); arcB = arclen(B[:n])
        sA = arcA / max(arcA[-1], 1e-6); sB = arcB / max(arcB[-1], 1e-6)
        for t in range(n):
            verts += [A[t], B[t]]
        nr = []
        for t in range(n):
            nr += [normals[i][t], normals[i + 1][t]]
        for t in range(n - 1):
            if np.linalg.norm(A[t + 1] - B[t + 1]) > max_gap or np.linalg.norm(A[t] - B[t]) > max_gap:
                continue
            a = 2 * t
            f = [a, a + 2, a + 3, a + 1]
            uvq = [(ua, vt + (vb - vt) * sA[t]), (ua, vt + (vb - vt) * sA[t + 1]), (ub, vt + (vb - vt) * sB[t + 1]), (ub, vt + (vb - vt) * sB[t])]
            vv = verts
            fnrm = np.cross(vv[a + 2] - vv[a], vv[a + 1] - vv[a])
            if np.dot(fnrm, normals[i][t] + normals[i + 1][t]) < 0:
                f = f[::-1]; uvq = uvq[::-1]
            faces.append(f); uvs.append(uvq)
        if not faces:
            continue
        nr = np.array(nr)
        part.add(np.array(verts), faces, "Hair", uvs, {"lnx": nr[:, 0], "lny": nr[:, 1], "lnz": nr[:, 2],
                                                       "layer": np.full(len(verts), float(layer)), "hairvol": np.zeros(len(verts))})


def orient_outward(obj, ctx):
    """Flip the faces of a garment mesh whose normals point towards the body (imported garments can have inverted
    collars / panels), so nearest-surface collisions push hair outwards."""
    import bmesh as _bm
    me = obj.data
    bm = _bm.new(); bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    flip = []
    for f in bm.faces:
        c = f.calc_center_median()
        hit, n, _, d = ctx.tree.find_nearest(c, 0.4)
        if hit is None:
            continue
        away = c - hit
        if away.length < 1e-5:
            away = n
        if f.normal.dot(away) < 0:
            flip.append(f)
    if flip:
        _bm.ops.reverse_faces(bm, faces=flip)
    bm.to_mesh(me); bm.free(); me.update()
    return len(flip)
