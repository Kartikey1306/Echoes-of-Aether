"""Kael Voss v2 outfit: techwear jacket + high collar, plate carrier with chest plate, segmented pauldrons,
right-forearm Aether interface, duty belt, cargo trousers with knee/shin guards, armoured boots, tech gloves.

Mesh names follow the game contract (CharacterModel toggles, armour-set 'replaces' lists):
  Top, Collar, ChestRig, ChestPlate, PauldronL, PauldronLameL, PauldronR, PauldronLameR, ForearmGuardR, Interface,
  Belt, Pants, KneePadL, KneePadR, Boots, Gloves
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
import kcommon as K
from kcommon import ss, nrm
import garment as G
import meshops

PRE = K.PRE


def limb_t(P, a, b):
    """Parameter along segment a->b and radial distance from its axis."""
    d = b - a
    L2 = d @ d
    t = (P - a) @ d / L2
    q = P - a - t[:, None] * d
    return t, np.linalg.norm(q, axis=1)


def select_faces(B, pred):
    """MakeHuman cage faces whose centre satisfies pred(centres, weights) -> bool array."""
    F = B.mh_faces
    C = np.array([B.mh_co[f].mean(0) for f in F])
    Wc = np.array([B.mh_W[f].mean(0) for f in F])
    m = np.asarray(pred(C, Wc), bool)
    return [i for i in range(len(F)) if m[i]]


class Outfit:
    def __init__(self, B):
        self.B = B
        self.L, self.T = B.L, B.T
        self.objs = {}

    # ------------------------------------------------------------------ jacket
    def top(self):
        B, L, T = self.B, self.L, self.T
        wb = lambda W, names: B.wsum(W, names)
        torso_b = ["Hips", "Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "LeftBreast", "RightBreast"]
        arm_b = [s + n for s in ("Left", "Right") for n in ("Arm", "ArmTwist", "ForeArm", "ForeArmTwist")]

        def pred(C, W):
            t = wb(W, torso_b + arm_b)
            hand = wb(W, ["LeftHand", "RightHand"])
            head = wb(W, ["Head", "Neck"])
            return (t > 0.45) & (hand < 0.5) & (head < 0.6) & (C[:, 2] > 0.9)
        o = G.shell_from_faces(B, select_faces(B, pred), "Top")
        neck_c = np.array((0.0, -0.005))

        def f_hem(P):
            back = ss(-0.04, 0.06, P[:, 1])
            hem = 0.985 - 0.035 * back
            return P[:, 2] - hem

        def f_neck(P):
            r = np.hypot(P[:, 0] - neck_c[0], (P[:, 1] - neck_c[1]) * 1.15)
            line = 1.545 + 0.04 * ss(-0.06, 0.05, P[:, 1])
            return np.maximum(line - P[:, 2], r - 0.082)

        def f_cuffs(P):
            out = np.full(len(P), 1.0)
            for s in ("Left", "Right"):
                t, r = limb_t(P, L[s + "ForeArm"], L[s + "Hand"])
                m = (t > 0.4) & (r < 0.09) & (np.sign(P[:, 0]) == np.sign(L[s + "Hand"][0]))
                out = np.where(m, np.minimum(out, 0.9 - t), out)
            return out
        for f in (f_hem, f_neck, f_cuffs):
            G.cut(o, f)
        G.drop_islands(o)

        def off(P, N):
            o_ = np.full(len(P), 0.0095)
            # padded yoke over the shoulders, a little room over chest/back and the stomach (fabric bridges it)
            o_ += 0.004 * ss(1.40, 1.50, P[:, 2]) * (np.abs(P[:, 0]) < 0.26)
            o_ += 0.002 * ss(1.0, 1.15, P[:, 2]) * (np.abs(P[:, 0]) < 0.2)
            for s in ("Left", "Right"):
                t, r = limb_t(P, L[s + "ForeArm"], L[s + "Hand"])
                m = (r < 0.1) & (np.sign(P[:, 0]) == np.sign(L[s + "Hand"][0]))
                o_ = np.where(m & (t > 0.0), o_ - 0.0015 + 0.003 * ss(0.65, 0.9, t), o_)   # forearm slimmer, cuff flare
            return o_
        G.relax_offset(o, B, off, iters=26, lam=0.5)
        G.rim(o, 0.0055)
        G.smooth_shading(o)
        G.set_material(o, "Garment_Top")
        G.unwrap(o)
        self.objs["Top"] = o
        B.push_layer(o)
        return o

    # ------------------------------------------------------------------ trousers
    def pants(self):
        B, L = self.B, self.L
        leg_b = ["Hips", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftButtock", "RightButtock", "Spine"]

        def pred(C, W):
            return (B.wsum(W, leg_b) > 0.5) & (C[:, 2] < 1.16) & (C[:, 2] > 0.2) & (B.wsum(W, ["LeftFoot", "RightFoot"]) < 0.3)
        o = G.shell_from_faces(B, select_faces(B, pred), "Pants")
        G.cut(o, lambda P: 1.105 - 0.01 * ss(-0.04, 0.06, P[:, 1]) - P[:, 2])     # waistband (under the jacket hem)
        G.cut(o, lambda P: P[:, 2] - 0.27)                                         # tucked into the boots
        G.drop_islands(o)

        def off(P, N):
            o_ = np.full(len(P), 0.0085)
            o_ += 0.004 * ss(0.62, 0.82, P[:, 2]) * (1 - ss(0.92, 1.0, P[:, 2]))   # thigh room (cargo cut)
            o_ += 0.002 * ss(0.5, 0.42, P[:, 2]) * ss(0.3, 0.38, P[:, 2])           # gather above the boots
            return o_
        G.relax_offset(o, B, off, iters=22, lam=0.5)
        G.rim(o, 0.005)
        G.smooth_shading(o)
        G.set_material(o, "Garment_Pants")
        G.unwrap(o)
        self.objs["Pants"] = o
        B.push_layer(o)
        return o


# ============================================================================= gear adapter + helpers
import gear


class GearCtx:
    """Adapter so the gear.py hard-surface tools (plate, strap, buckle, pouch...) cast onto the current outer surface."""

    def __init__(self, B):
        self.B = B

    def outer_tree(self):
        return self.B.outer_tree()

    def cast(self, origin, direction, dist=1.0, tree=None):
        tree = tree or self.outer_tree()
        hit, n, _, d = tree.ray_cast(Vector(origin), Vector(direction).normalized(), dist)
        return (np.array(hit), np.array(n)) if hit is not None else (None, None)

    def nearest(self, p, tree=None, dist=1.0):
        tree = tree or self.outer_tree()
        hit, n, _, d = tree.find_nearest(Vector(p), dist)
        return (np.array(hit), np.array(n)) if hit is not None else (np.array(p), np.array((0, 0, 1.0)))


def surf(ctx, origin, direction, dist=0.6):
    """First outer-surface hit casting from origin + direction * dist back towards origin."""
    d = nrm(direction)
    hit, n = ctx.cast(np.asarray(origin) + d * dist, -d, dist + 0.05)
    return hit, n


def ring_points(ctx, c, axis, ref, n=32, R=0.25, push=0.0, phi0=0.0, phi1=2 * math.pi, closed=True):
    """Points on the outer surface around an axis through c (rays from outside towards the axis)."""
    ax = nrm(axis)
    r0 = nrm(np.asarray(ref) - ax * (np.asarray(ref) @ ax))
    r1 = np.cross(ax, r0)
    pts, nrms = [], []
    cnt = n if closed else n
    for k in range(cnt):
        phi = phi0 + (phi1 - phi0) * k / (n if closed else n - 1)
        d = r0 * math.cos(phi) + r1 * math.sin(phi)
        hit, hn = ctx.cast(np.asarray(c) + d * R, -d, R + 0.02)
        if hit is None:
            hit, hn = np.asarray(c) + d * 0.08, d
        pts.append(hit + d * push)
        nrms.append(d)
    return np.array(pts), np.array(nrms)


def band_mesh(name, rows, mat, closed=True, uv_scale=4.0):
    """Quad strip mesh from rows of points (list of (n,3) arrays)."""
    part = gear.Part(name)
    verts = np.vstack(rows)
    n = len(rows[0])
    faces, uvs = [], []
    L = [0.0]
    for k in range(1, n + (1 if closed else 0)):
        L.append(L[-1] + np.linalg.norm(rows[0][k % n] - rows[0][k - 1]))
    for r in range(len(rows) - 1):
        for k in range(n if closed else n - 1):
            k2 = (k + 1) % n
            faces.append([r * n + k, r * n + k2, (r + 1) * n + k2, (r + 1) * n + k])
            v0 = r * 0.03 * uv_scale; v1 = (r + 1) * 0.03 * uv_scale
            uvs.append([(L[k] * uv_scale, v0), (L[k + 1] * uv_scale, v0), (L[k + 1] * uv_scale, v1), (L[k] * uv_scale, v1)])
    part.add(verts, faces, mat, uvs)
    return part


# ============================================================================= soft gear: collar, plate carrier


def collar(self):
    B, L = self.B, self.L
    ctx = GearCtx(B)
    c0 = np.array((0.0, -0.006, 0.0))
    n = 44
    phis = np.radians(np.linspace(18, 360 - 14, n))       # opening just right of centre (asymmetric front)
    back = lambda ph: 0.5 - 0.5 * np.cos(ph)               # 0 front .. 1 back
    rows = []
    heights = [0.0, 0.33, 0.66, 1.0]
    for hk in heights:
        row = []
        for ph in phis:
            bz = 1.552 + 0.036 * back(ph)
            tz = 1.622 + 0.04 * back(ph)
            z = bz + (tz - bz) * hk
            d = np.array((math.sin(ph), -math.cos(ph), 0.0))
            c = np.array((c0[0], c0[1], z))
            hit, hn = ctx.cast(c + d * 0.2, -d, 0.21)
            r_hit = np.linalg.norm((hit - c)[:2]) if hit is not None else 0.07
            gap = 0.004 + 0.009 * hk
            r = r_hit + gap
            row.append(c + d * r)
        rows.append(np.array(row))
    # flare: the top ring leans out a little and never inside the ring below minus 4 mm
    for k in range(n):
        r_prev = np.linalg.norm(rows[-2][k][:2] - c0[:2])
        r_top = np.linalg.norm(rows[-1][k][:2] - c0[:2])
        want = max(r_top, r_prev - 0.002)
        d = nrm(np.array((rows[-1][k][0] - c0[0], rows[-1][k][1] - c0[1], 0)))
        rows[-1][k] = np.array((c0[0], c0[1], rows[-1][k][2])) + d * want
    part = band_mesh("Collar", rows, "Garment_Top", closed=False)
    o = part.build()
    sol = o.modifiers.new("sol", "SOLIDIFY")
    sol.thickness = 0.006
    sol.offset = -1.0
    sol.use_even_offset = True
    gear.apply_modifiers(o)
    G.smooth_shading(o)
    sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = 1
    gear.apply_modifiers(o)
    self.objs["Collar"] = o
    B.push_layer(o)
    return o


def chest_rig(self):
    B, L = self.B, self.L
    torso_b = ["Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "LeftBreast", "RightBreast", "Neck"]
    arm_b = [s + n for s in ("Left", "Right") for n in ("Arm", "ArmTwist", "ForeArm", "ForeArmTwist")]

    def pred(C, W):
        return (B.wsum(W, torso_b) > 0.4) & (B.wsum(W, arm_b) < 0.35) & (C[:, 2] > 1.12) & (C[:, 2] < 1.64) & (B.wsum(W, ["Head"]) < 0.1)
    o = G.shell_from_faces(B, select_faces(B, pred), "ChestRig")

    def field(P):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        top_f = 1.468 - 0.075 * ss(0.065, 0.15, ax) - 0.022 * (1 - ss(0.0, 0.06, ax))
        f_front = np.minimum.reduce([-y - 0.02, 0.152 - ax, z - 1.218, top_f - z])
        top_b = 1.505 - 0.065 * ss(0.07, 0.16, ax)
        f_back = np.minimum.reduce([y - 0.0, 0.158 - ax, z - 1.205, top_b - z])
        f_strap = np.minimum(0.026 - np.abs(ax - 0.098), z - 1.40)
        f_cumm = np.minimum(z - 1.195, 1.315 - z)
        return np.maximum.reduce([f_front, f_back, f_strap, f_cumm])
    G.cut(o, field)
    G.drop_islands(o, 20)

    def off(P, N):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        panel = (ax < 0.13) & (z > 1.24) & (z < 1.45)
        o_ = np.full(len(P), 0.026)
        o_ += 0.008 * panel
        o_ -= 0.006 * ((z > 1.47) & (ax > 0.06))           # straps lie flatter
        return o_

    def gap(P, N):
        return off(P, N) - 0.011
    G.relax_offset(o, B, off, iters=30, lam=0.55, min_gap_fn=gap)
    G.rim(o, 0.008)
    G.smooth_shading(o)
    G.set_material(o, "Garment_Top")
    G.unwrap(o)
    self.objs["ChestRig"] = o
    B.push_layer(o)
    # magazine / utility pouches on the lower front (Cloth_Gear), merged into ChestRig
    ctx = GearCtx(B)
    pp = gear.Part("ChestRigPouches")
    for x in (-0.072, 0.0, 0.072):
        hit, hn = surf(ctx, np.array((x, 0.0, 1.265)), (0, -1, 0), 0.4)
        if hit is None:
            continue
        gear.pouch(ctx, pp, hit, nrm(hn + np.array((0, -0.4, 0))), (0, 0, 1), 0.062, 0.095, 0.03, mat="Cloth_Gear", snap=True)
    po = pp.build()
    self.objs["ChestRig"] = gear.join([o, po], "ChestRig")
    self.B._outer = None
    return self.objs["ChestRig"]


Outfit.collar = collar
Outfit.chest_rig = chest_rig


# ============================================================================= hard surface


def chest_plate(self):
    B = self.B
    ctx = GearCtx(B)
    part = gear.Part("ChestPlate")
    piv = np.array((0.0, 0.07, 1.33))
    # two angular pectoral plates split by a centre channel (layer 1)
    for sd in (1, -1):
        hit, hn = surf(ctx, np.array((sd * 0.066, 0.0, 1.392)), nrm((sd * 0.25, -1, 0.1)), 0.5)
        if hit is None:
            continue
        poly = [(-1, 0.35), (-0.55, 1), (1, 1), (1, -0.25), (0.62, -1), (-0.6, -1), (-1, -0.55)]
        if sd < 0:
            poly = [(-x, y) for (x, y) in poly][::-1]
        gear.plate(ctx, part, hit, nrm(hn + np.array((0, -0.5, 0.05))), (0, 0, 1), 0.06, 0.068, offset=0.008, thickness=0.009, crown=0.009,
                   chamfer=0.0034, poly=poly, corner=0.1, groove=0.76, groove_depth=0.0013, segs=44, plate_id=10 + (sd > 0), zone=0,
                   edge_zone=2, mode="radial", pivot=piv + np.array((sd * 0.03, 0, 0)), cast_r=0.45, clearance=0.003,
                   bolts=[(sd * -0.72, 0.62), (sd * 0.75, -0.7)], vents=[(sd * 0.25, -0.58, 0.45, 0.24, 4)],
                   inlay=(0.55, 0.68) if sd > 0 else None, inlay_mat="Glow")
    o = part.build()
    B.push_layer(o)
    # sternum spine + collarbone yoke plates (layer 2)
    part2 = gear.Part("ChestPlateYoke")
    hit, hn = surf(ctx, np.array((0.0, 0.0, 1.43)), (0, -1, 0.15), 0.5)
    if hit is not None:
        gear.plate(ctx, part2, hit, nrm(hn), (0, 0, 1), 0.02, 0.05, offset=0.004, thickness=0.007, crown=0.004, chamfer=0.0025,
                   poly=[(-1, 1), (1, 1), (0.7, -1), (-0.7, -1)], corner=0.15, segs=28, plate_id=12, zone=1, edge_zone=2,
                   bolts=[(0.0, 0.62)], clearance=0.002, groove=0.6, groove_depth=0.0009, inlay=(0.3, 0.45), inlay_mat="Glow")
    for sd in (1, -1):
        hit, hn = surf(ctx, np.array((sd * 0.088, 0.0, 1.468)), nrm((sd * 0.15, -1, 0.45)), 0.5)
        if hit is None:
            continue
        poly = [(-1, 1), (1, 1), (1, -0.3), (0.5, -1), (-1, -1)]
        if sd < 0:
            poly = [(-x, y) for (x, y) in poly][::-1]
        gear.plate(ctx, part2, hit, nrm(hn + np.array((0, -0.2, 0.3))), nrm((-sd * 0.3, 0, 1)), 0.052, 0.024, offset=0.004, thickness=0.006,
                   crown=0.004, chamfer=0.0025, poly=poly, corner=0.12, segs=32, plate_id=13 + (sd > 0), zone=1, edge_zone=2,
                   bolts=[(-0.7, 0.15), (0.7, 0.15)], clearance=0.002)
    o2 = part2.build()
    o = gear.join([o, o2], "ChestPlate")
    self.objs["ChestPlate"] = o
    B._outer = None
    return o


def _pauldron(self, side, scale=1.0):
    B, L = self.B, self.L
    ctx = GearCtx(B)
    S = "Left" if side > 0 else "Right"
    sh = L[S + "Arm"]
    el = L[S + "ForeArm"]
    arm = nrm(el - sh)
    piv = sh + np.array((-side * 0.02, 0.0, -0.01))
    cap = gear.Part("Pauldron" + ("L" if side > 0 else "R"))
    d = nrm(np.array((side * 1.0, -0.05, 0.75)))
    hit, hn = surf(ctx, piv, d, 0.3)
    up = nrm(-arm + np.array((0, 0, 0.3)))
    gear.plate(ctx, cap, hit, d, up, 0.1 * scale, 0.088 * scale, offset=0.011, thickness=0.009, crown=0.02, chamfer=0.0036,
               poly=[(-1, 0.6), (-0.62, 1), (0.62, 1), (1, 0.6), (0.95, -0.4), (0.45, -1), (-0.45, -1), (-0.95, -0.4)], corner=0.12,
               groove=0.72, groove_depth=0.0012, segs=48, plate_id=20 + (side > 0), zone=0, edge_zone=2, mode="radial", pivot=piv,
               cast_r=0.3, bolts=[(-0.8, 0.55), (0.8, 0.55)], rivets=True, clearance=0.004,
               inlay=(0.55, 0.7) if side > 0 else None, inlay_mat="Glow")
    capo = cap.build()
    B.push_layer(capo)
    # two overlapping lames down the upper arm, hinged to the cap
    lam = gear.Part("PauldronLame" + ("L" if side > 0 else "R"))
    for k, (t, a_, off) in enumerate(((0.28, 0.084, 0.012), (0.43, 0.078, 0.01))):
        c = sh + (el - sh) * t
        dd = nrm(np.array((side * 1.0, -0.1, 0.0)) - arm * (np.array((side * 1.0, -0.1, 0.0)) @ arm))
        hit, hn = surf(ctx, c, dd, 0.2)
        if hit is None:
            continue
        gear.plate(ctx, lam, hit, dd, -arm, a_ * scale, 0.026 * scale, offset=off, thickness=0.006, crown=0.005, chamfer=0.0028,
                   poly=[(-1, 1), (1, 1), (0.9, -1), (-0.9, -1)], corner=0.12, segs=36, plate_id=22 + k, zone=0 if k == 0 else 1, edge_zone=2,
                   mode="radial", pivot=c, cast_r=0.2, clearance=0.003, rivets=False, bolts=[(-0.85, 0.0), (0.85, 0.0)])
    # hinge barrels at the front and back of the cap's lower edge, and a small piston at the back
    fr = nrm(np.cross(arm, np.array((0, 0, 1.0)))) * (1 if side > 0 else -1)
    for sgn in (1, -1):
        p = sh + (el - sh) * 0.2 + np.array((side * 0.06, 0, 0)) + np.array((0, sgn * 0.055, 0.0))
        hit, hn = surf(ctx, p, nrm(np.array((side * 0.6, sgn * 0.8, 0.0))), 0.15)
        if hit is None:
            continue
        hp = hit + hn * 0.012
        gear.hinge(lam, hp - arm * 0.012, hp + arm * 0.012, radius=0.0042, knuckles=3, mat="Armor", zone=2)
    p0 = sh + (el - sh) * 0.12 + np.array((side * 0.05, 0.06, 0.02))
    h0, n0 = surf(ctx, p0, nrm(np.array((side * 0.5, 1.0, 0.2))), 0.15)
    p1 = sh + (el - sh) * 0.42 + np.array((side * 0.04, 0.05, 0.0))
    h1, n1 = surf(ctx, p1, nrm(np.array((side * 0.5, 1.0, 0.0))), 0.15)
    if h0 is not None and h1 is not None:
        gear.piston(lam, h0 + n0 * 0.014, h1 + n1 * 0.013, r_house=0.0045, r_rod=0.0022, zone=2)
    lamo = lam.build()
    self.objs[capo.name] = capo
    self.objs[lamo.name] = lamo
    B.push_layer(lamo)
    return capo, lamo


def pauldrons(self):
    _pauldron(self, 1, 1.0)
    _pauldron(self, -1, 0.92)


Outfit.chest_plate = chest_plate
Outfit.pauldrons = pauldrons


def forearm_r(self):
    """Right-forearm Aether interface: three articulated bracer segments, a framed holo screen with UI light bars,
    an emitter ring at the wrist and conduits along the arm."""
    B, L = self.B, self.L
    ctx = GearCtx(B)
    E, W = L["RightForeArm"], L["RightHand"]
    ax = nrm(W - E)
    wr, dors, fdir, mcp = gear.hand_frame(L, -1)
    up = nrm(dors - ax * (dors @ ax))                       # dorsal side of the forearm
    lat = nrm(np.cross(ax, up))
    guard = gear.Part("ForearmGuardR")
    segs = ((0.2, 0.43, 0.050, 0.009), (0.41, 0.66, 0.054, 0.012), (0.64, 0.86, 0.050, 0.010))
    frames = []
    for k, (t0, t1, a_, off) in enumerate(segs):
        tc = (t0 + t1) / 2
        c = E + (W - E) * tc
        d = nrm(up * 0.85 + lat * 0.35)
        hit, hn = surf(ctx, c, d, 0.15)
        if hit is None:
            continue
        fr = gear.plate(ctx, guard, hit, d, ax, a_, (t1 - t0) * np.linalg.norm(W - E) * 0.5, offset=off, thickness=0.007, crown=0.006,
                        chamfer=0.003, poly=[(-1, 1), (1, 1), (1, -1), (-1, -1)], corner=0.3, segs=40, plate_id=30 + k, zone=k % 2,
                        edge_zone=2, mode="radial", pivot=c, cast_r=0.15, clearance=0.003, groove=0.7 if k != 1 else 0.0,
                        bolts=[(-0.8, 0.75), (0.8, 0.75), (-0.8, -0.75), (0.8, -0.75)] if k != 1 else [], rivets=k == 0)
        frames.append((k, c, d, fr))
    # emitter ring at the wrist end
    ring_c = E + (W - E) * 0.9
    pts, nr = ring_points(ctx, ring_c, ax, up, n=28, R=0.15, push=0.007)
    pts = np.vstack([pts, pts[:1]])
    gear.tube(guard, pts, 0.0055, 10, mat="Armor", attrs={"mz": 2.0, "wear": 0.8})
    pts2, _ = ring_points(ctx, ring_c - ax * 0.008, ax, up, n=28, R=0.15, push=0.0105)
    pts2 = np.vstack([pts2, pts2[:1]])
    gear.tube(guard, pts2, 0.0018, 6, mat="Glow")
    # conduits from the elbow segment to the emitter (two metal lines, one restrained magenta light pipe)
    for k, (sgn, mat, rad) in enumerate(((1, "Metal", 0.0026), (-1, "Metal", 0.0026), (0.0, "Glow2", 0.0013))):
        P = []
        for t in np.linspace(0.22, 0.88, 14):
            c = E + (W - E) * t
            dd = nrm(up * 0.5 + lat * (0.9 * sgn if sgn else -0.95))
            hit, hn = surf(ctx, c, dd, 0.15)
            if hit is not None:
                P.append(hit + hn * (0.006 if mat != "Glow2" else 0.004))
        if len(P) > 3:
            gear.tube(guard, np.array(P), rad, 8 if mat != "Glow2" else 6, mat=mat, caps=True)
    go = guard.build()
    B.push_layer(go)
    self.objs["ForearmGuardR"] = go
    # holo interface on the middle segment
    ui = gear.Part("Interface")
    k, c, d, fr = frames[1]
    hit, hn = surf(ctx, c, d, 0.15)
    n_ = nrm(hn)
    u_ = nrm(ax - n_ * (ax @ n_))
    r_ = np.cross(u_, n_)
    base = hit + n_ * 0.004
    gear.rbox(ui, base + n_ * 0.004, r_, u_, n_, (0.05, 0.068, 0.008), bevel=0.0025, segments=2, mat="Armor", attrs={"mz": 1.0, "wear": 0.6})
    gear.rbox(ui, base + n_ * 0.0082, r_, u_, n_, (0.04, 0.056, 0.0016), bevel=0.0008, segments=1, mat="Screen")
    # UI: light bars and a status arc, floating just above the glass
    top = base + n_ * 0.0092
    for j, (w, y) in enumerate(((0.03, 0.019), (0.022, 0.011), (0.026, 0.003), (0.014, -0.005))):
        gear.rbox(ui, top + r_ * (-0.004 + (0.03 - w) * -0.5) + u_ * y, r_, u_, n_, (w, 0.0022, 0.0006), bevel=0.0, segments=0, mat="Glow")
    arc = [top + u_ * (-0.017 + 0.009 * math.sin(a)) + r_ * (0.009 * math.cos(a)) for a in np.linspace(0.3, 2 * math.pi - 0.6, 18)]
    gear.tube(ui, np.array(arc), 0.0009, 5, mat="Glow2")
    uo = ui.build()
    self.objs["Interface"] = uo
    return go, uo


def belt(self):
    B = self.B
    ctx = GearCtx(B)
    part = gear.Part("Belt")
    c = np.array((0.0, 0.0, 0.0))
    rows = []
    for z in (0.992, 1.012, 1.032):
        pts, _ = ring_points(ctx, np.array((0.0, -0.01, z)), (0, 0, 1), (0, -1, 0), n=48, R=0.35, push=0.006)
        rows.append(pts)
    bp = band_mesh("BeltBand", rows, "Cloth_Gear")
    bo = bp.build()
    sol = bo.modifiers.new("sol", "SOLIDIFY"); sol.thickness = 0.005; sol.offset = 1.0; sol.use_even_offset = True
    gear.apply_modifiers(bo)
    B.push_layer(bo)
    # buckle
    hit, hn = surf(ctx, np.array((0.0, 0.0, 1.012)), (0, -1, 0), 0.4)
    if hit is not None:
        r_, u_, n_ = gear.frame_from(hn, (0, 0, 1))
        gear.rbox(part, hit + n_ * 0.009, r_, u_, n_, (0.058, 0.046, 0.009), bevel=0.0028, segments=2, mat="Metal", attrs={"wear": 1.0})
        gear.rbox(part, hit + n_ * 0.0145, r_, u_, n_, (0.036, 0.026, 0.0025), bevel=0.0009, segments=1, mat="Armor", attrs={"mz": 1.0})
        gear.rbox(part, hit + n_ * 0.016, r_, u_, n_, (0.022, 0.0028, 0.001), bevel=0.0, segments=0, mat="Glow")
    # pouches: left hip, right hip (two), back utility
    for (phi, w, h, d) in ((48, 0.075, 0.09, 0.032), (-50, 0.065, 0.08, 0.03), (-82, 0.05, 0.075, 0.028), (180, 0.11, 0.07, 0.03)):
        ph = math.radians(phi)
        dd = np.array((math.sin(ph), -math.cos(ph), 0.0))
        hit, hn = surf(ctx, np.array((0.0, -0.01, 0.99)), dd, 0.4)
        if hit is None:
            continue
        gear.pouch(ctx, part, hit - np.array((0, 0, 0.03)), nrm(np.array((hn[0], hn[1], 0))), (0, 0, 1), w, h, d, mat="Cloth_Gear", snap=True)
    po = part.build()
    o = gear.join([bo, po], "Belt")
    B._outer = None
    self.objs["Belt"] = o
    return o


def knee_pads(self):
    B, L = self.B, self.L
    ctx = GearCtx(B)
    for side, S in ((1, "Left"), (-1, "Right")):
        K_ = L[S + "Leg"]
        A_ = L[S + "Foot"]
        H_ = L[S + "UpLeg"]
        shin = nrm(A_ - K_)
        part = gear.Part("KneePad" + ("L" if side > 0 else "R"))
        d = nrm(np.array((side * 0.12, -1.0, 0.05)))
        piv = K_ + np.array((0, 0.015, 0.0))
        hit, hn = surf(ctx, piv, d, 0.25)
        gear.plate(ctx, part, hit, d, nrm(-shin + np.array((0, 0, 0.3))), 0.05, 0.054, offset=0.007, thickness=0.008, crown=0.014,
                   chamfer=0.003, poly=[(-0.75, 1), (0.75, 1), (1, 0.45), (1, -0.45), (0.45, -1), (-0.45, -1), (-1, -0.45), (-1, 0.45)], corner=0.15,
                   groove=0.7, segs=44, plate_id=40, zone=0, edge_zone=2, mode="radial", pivot=piv, cast_r=0.25, clearance=0.003,
                   bolts=[(-0.75, 0.0), (0.75, 0.0)], vents=[(0.0, 0.35, 0.5, 0.22, 3)])
        # shin guard under the knee cap
        cs = K_ + (A_ - K_) * 0.27
        d2 = nrm(np.array((side * 0.1, -1.0, 0.0)))
        hit, hn = surf(ctx, cs, d2, 0.2)
        if hit is not None:
            gear.plate(ctx, part, hit, d2, -shin, 0.04, 0.062, offset=0.005, thickness=0.007, crown=0.007, chamfer=0.0028,
                       poly=[(-1, 1), (1, 1), (0.85, -0.6), (0.3, -1), (-0.3, -1), (-0.85, -0.6)], corner=0.3, segs=40, plate_id=41,
                       zone=1, edge_zone=2, mode="radial", pivot=cs + np.array((0, 0.02, 0)), cast_r=0.2, clearance=0.003, rivets=True,
                       groove=0.68, groove_depth=0.001)
        # side straps
        for zt in (0.12, 0.48):
            cc = K_ + (A_ - K_) * zt
            pts, nr = ring_points(ctx, cc, shin, (0, -1, 0), n=20, R=0.2, push=0.0025, phi0=math.radians(-100), phi1=math.radians(100), closed=False)
            gear.strap(part, pts, nr, 0.016, 0.0028, mat="Cloth_Gear", caps=True)
        o = part.build()
        self.objs[o.name] = o
    return True


Outfit.forearm_r = forearm_r
Outfit.belt = belt
Outfit.knee_pads = knee_pads


def _sole(part, loop_pts, heel_y, toe_y, cx):
    """Chunky cup sole from the boot upper's bottom boundary loop: bevelled slab, heel lift, toe spring."""
    P = np.asarray(loop_pts)
    cy = (P[:, 1].min() + P[:, 1].max()) * 0.5
    n = 48
    outline = []
    for k in range(n):
        phi = 2 * math.pi * k / n
        d = np.array((math.sin(phi), -math.cos(phi)))
        proj = (P[:, :2] - np.array((cx, cy))) @ d
        outline.append(np.array((cx, cy)) + d * (np.percentile(proj, 96) + 0.003))
    outline = np.array(outline)
    for _ in range(5):
        outline = outline * 0.5 + (np.roll(outline, 1, 0) + np.roll(outline, -1, 0)) * 0.25
    ymin, ymax = outline[:, 1].min(), outline[:, 1].max()
    verts, faces, uvs, sharp = [], [], [], []
    rings = [(-0.004, 0.0), (0.0, -0.002), (0.0035, -0.006), (0.0055, -0.014), (0.004, -0.026), (0.0, -0.033), (-0.007, -0.035)]
    for (ox, oy) in outline:
        heel = ss(ymax - 0.1, ymax - 0.04, oy)
        spring = 0.01 * ss(ymin + 0.06, ymin, oy)
        top = 0.036 + 0.01 * heel + spring * 0.4
        bottom = 0.0 + spring
        d = nrm(np.array((ox - cx, oy - cy, 0.0)))
        for (out_, dz) in rings:
            zz = top + dz * (top - bottom) / 0.035
            verts.append((ox + d[0] * out_, oy + d[1] * out_, zz))
    R_ = len(rings)
    for k in range(n):
        k2 = (k + 1) % n
        for r in range(R_ - 1):
            a, b = k * R_ + r, k2 * R_ + r
            faces.append([a, a + 1, b + 1, b])
            uvs.append([(k / n * 2, 1 - r / R_ * 0.3), (k / n * 2, 1 - (r + 1) / R_ * 0.3), ((k + 1) / n * 2, 1 - (r + 1) / R_ * 0.3), ((k + 1) / n * 2, 1 - r / R_ * 0.3)])
        sharp += [(k * R_ + 2, k2 * R_ + 2), (k * R_ + 5, k2 * R_ + 5)]
    c = len(verts); verts.append((cx, cy, 0.0))
    for k in range(n):
        a_ = k * R_ + R_ - 1; b_ = ((k + 1) % n) * R_ + R_ - 1
        faces.append([a_, c, b_])
        uvs.append([((verts[a_][0] - cx) * 4 + 0.5, (verts[a_][1] - cy) * 4 + 0.5), (0.5, 0.5), ((verts[b_][0] - cx) * 4 + 0.5, (verts[b_][1] - cy) * 4 + 0.5)])
    part.add(np.array(verts), faces, "Boots", uvs, {"sole": 1.0}, sharp)
    return outline


def boots(self):
    B, L = self.B, self.L
    ctx = GearCtx(B)
    foot_b = ["LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase", "LeftLeg", "RightLeg"]

    def pred(C, W):
        return (B.wsum(W, foot_b) > 0.5) & (C[:, 2] < 0.38)
    o = G.shell_from_faces(B, select_faces(B, pred), "Boots")
    G.cut(o, lambda P: 0.312 - P[:, 2] - 0.012 * ss(-0.02, 0.06, P[:, 1] - L["LeftFoot"][1]))
    G.cut(o, lambda P: P[:, 2] - 0.012)
    G.drop_islands(o, 20)

    def off(P, N):
        o_ = np.full(len(P), 0.0095)
        toe = ss(0.0, -0.08, P[:, 1] - L["LeftFoot"][1])
        o_ += 0.0025 * toe + 0.002 * ss(0.14, 0.06, P[:, 2]) * ss(0.02, 0.05, P[:, 2])
        return o_
    G.relax_offset(o, B, off, iters=34, lam=0.6)
    co_ = K.get_co(o)
    co_[:, 2] = np.maximum(co_[:, 2], 0.03) + np.maximum(0.0, 0.034 - co_[:, 2]) * 0.0   # the upper ends on the sole
    K.set_co(o, co_)
    G.drop_degenerate(o)
    G.rim(o, 0.006)
    G.smooth_shading(o)
    G.set_material(o, "Boots")
    G.unwrap(o)
    B.push_layer(o)
    # soles + armour
    co = K.get_co(o)
    E, bE, isb = G.boundary_info(o)
    part = gear.Part("BootsDetail")
    for side, S in ((1, "Left"), (-1, "Right")):
        an = L[S + "Foot"]; toe = L[S + "ToeBase"]
        sel = isb & (np.sign(co[:, 0]) == side) & (co[:, 2] < 0.06)
        if sel.sum() < 6:
            continue
        _sole(part, co[sel], 0, 0, an[0])
        # toe cap
        tc = toe + np.array((0, -0.035, 0.0))
        tc[2] = 0.05
        hit, hn = surf(ctx, tc + np.array((0, 0.02, 0)), (0, -1, 0.35), 0.2)
        if hit is not None:
            gear.plate(ctx, part, hit, nrm(hn), (0, 0, 1), 0.046, 0.03, n_exp=2.6, offset=0.002, thickness=0.004, crown=0.003, chamfer=0.002,
                       mat_top="Boots", mat_edge="Boots", mat_wall="Boots", segs=32, clearance=0.0015, cast_r=0.15, attrs={"cap": 1.0},
                       plate_id=60, mode="radial", pivot=np.array((toe[0], toe[1] + 0.02, 0.04)))
        # heel counter
        hh, hn = surf(ctx, np.array((an[0], an[1] + 0.02, 0.07)), (0, 1, 0), 0.25)
        if hh is not None:
            gear.plate(ctx, part, hh, hn, (0, 0, 1), 0.045, 0.035, n_exp=2.8, offset=0.002, thickness=0.004, crown=0.0, chamfer=0.002,
                       mat_top="Boots", mat_edge="Boots", mat_wall="Boots", segs=28, clearance=0.0012, cast_r=0.15, attrs={"cap": 1.0},
                       plate_id=61, mode="radial", pivot=np.array((an[0], an[1] - 0.01, 0.07)))
        # ankle/shaft armour plate (front) and two straps with buckles
        cf = np.array((an[0], an[1] - 0.02, 0.2))
        hit, hn = surf(ctx, cf, (0, -1, 0), 0.25)
        if hit is not None:
            gear.plate(ctx, part, hit, nrm(hn + np.array((0, -0.3, 0))), (0, 0, 1), 0.036, 0.07, offset=0.004, thickness=0.005, crown=0.005,
                       chamfer=0.0025, poly=[(-1, 1), (1, 1), (0.9, -0.5), (0, -1), (-0.9, -0.5)], corner=0.25, mode="radial",
                       pivot=np.array((an[0], an[1] + 0.01, 0.2)), cast_r=0.15, plate_id=62, segs=32, mat_top="Boots", mat_edge="Boots",
                       mat_wall="Boots", zone=1, edge_zone=2, rivets=True, clearance=0.003)
        for zz, ww in ((0.115, 0.024), (0.245, 0.022)):
            pts, nr = ring_points(ctx, np.array((an[0], an[1] + 0.005, zz)), (0, 0, 1), (0, -1, 0), n=26, R=0.15, push=0.001)
            pts = np.vstack([pts, pts[:1]]); nr = np.vstack([nr, nr[:1]])
            gear.strap(part, pts, nr, ww, 0.003, mat="Boots", attrs={"strap": 1.0})
            i = 7 if side > 0 else 19
            gear.buckle(part, pts[i] + nr[i] * 0.003, pts[i + 1] - pts[i], nr[i], ww, mat="Metal")
    do = part.build()
    o = gear.join([o, do], "Boots")
    B._outer = None
    self.objs["Boots"] = o
    return o


def gloves(self):
    B, L = self.B, self.L
    ctx = GearCtx(B)
    hand_names = [n[len(PRE):] for n in B.names if "Hand" in n]
    fore = ["LeftForeArm", "LeftForeArmTwist", "RightForeArm", "RightForeArmTwist"]

    def pred(C, W):
        h = B.wsum(W, hand_names)
        f = B.wsum(W, fore)
        near = np.zeros(len(C), bool)
        for s in ("Left", "Right"):
            t, r = limb_t(C, L[s + "ForeArm"], L[s + "Hand"])
            near |= (t > 0.7) & (r < 0.08) & (np.sign(C[:, 0]) == np.sign(L[s + "Hand"][0]))
        return (h > 0.35) | ((f > 0.3) & near)
    o = G.shell_from_faces(B, select_faces(B, pred), "Gloves")

    def f_cuff(P):
        out = np.full(len(P), 1.0)
        for s in ("Left", "Right"):
            t, r = limb_t(P, L[s + "ForeArm"], L[s + "Hand"])
            m = (r < 0.09) & (np.sign(P[:, 0]) == np.sign(L[s + "Hand"][0])) & (t < 1.0)
            out = np.where(m, np.minimum(out, t - 0.8), out)
        return out
    G.cut(o, f_cuff)
    G.drop_islands(o, 20)
    HF = {s: gear.hand_frame(L, s) for s in (1, -1)}

    def off(P, N):
        o_ = np.zeros(len(P))
        for s in (1, -1):
            S = "Left" if s > 0 else "Right"
            wr, dors, fdir, mcp = HF[s]
            m = np.sign(P[:, 0]) == s
            along = (P - wr) @ fdir
            t, r = limb_t(P, L[S + "ForeArm"], L[S + "Hand"])
            dn = N @ dors
            v = 0.0026 - 0.0008 * ss(0.09, 0.16, along)
            v += 0.0012 * ss(0.2, 0.6, dn) * ss(0.0, 0.03, along) * ss(0.09, 0.06, along)
            v += 0.0016 * ss(-0.2, -0.6, dn) * ss(0.1, 0.05, along) * ss(-0.01, 0.02, along)
            v += 0.0055 * ss(0.98, 0.84, t) * (t < 1.0)
            o_ = np.where(m, v, o_)
        return o_
    G.relax_offset(o, B, off, iters=4, lam=0.25, bsmooth=6)
    G.rim(o, 0.0028)
    G.smooth_shading(o)
    G.set_material(o, "Gloves")
    G.unwrap(o)
    B.push_layer(o)
    part = gear.Part("GloveArmor")
    for s in (1, -1):
        wr, dors, fdir, mcp = HF[s]
        if len(mcp) < 2:
            continue
        kc = np.mean(mcp, axis=0) - fdir * 0.003
        w_ = np.linalg.norm(mcp[0] - mcp[-1]) * 0.6 + 0.008
        gear.plate(ctx, part, kc, dors, fdir, w_, 0.0105, offset=0.0016, thickness=0.0045, crown=0.0016, chamfer=0.0016,
                   poly=[(-1, 1), (1, 1), (1, -1), (-1, -1)], corner=0.35, mat_top="Gloves", mat_edge="Gloves", mat_wall="Gloves", plate_id=90,
                   segs=24, cast_r=0.05, clearance=0.0015, bolts=[(-0.8, 0.0), (0.8, 0.0)], zone=1, edge_zone=2)
        bc = wr + fdir * 0.045
        gear.plate(ctx, part, bc, dors, fdir, 0.023, 0.021, offset=0.0016, thickness=0.004, crown=0.0016, chamfer=0.0015,
                   poly=[(-0.8, 1), (0.8, 1), (1, -0.6), (0, -1), (-1, -0.6)], corner=0.3, groove=0.62, groove_depth=0.0007,
                   mat_top="Gloves", mat_edge="Gloves", mat_wall="Gloves", plate_id=91, segs=24, cast_r=0.05, clearance=0.0015, zone=2, edge_zone=2)
    po = part.build()
    K.get_co(po)
    a = po.data.attributes.new("kplate", "FLOAT", "POINT")
    a.data.foreach_set("value", np.ones(len(po.data.vertices), np.float32))
    o = gear.join([o, po], "Gloves")
    B._outer = None
    self.objs["Gloves"] = o
    return o


Outfit.boots = boots
Outfit.gloves = gloves
