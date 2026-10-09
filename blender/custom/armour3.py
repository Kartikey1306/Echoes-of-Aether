"""Armour sets v3 (AAA rebuild): themed silhouettes, a detailed high-poly baked down onto the game mesh, and
physically based materials with real variety.

  blender -b --python blender/custom/armour3.py -- <cid> [set,...] [--no-export] [--size 2048]

Pipeline per set
  1. Game mesh (LP, <= 35k tris): under-suit fitted to the body (same skin weights, never pokes through) + hard
     panels/plates + theme pieces (plate carrier and pouches, exo struts and pistons, lacquered lamellae with cord
     lacing, cable-laced harness, winged pauldrons, shoulder emitters...). Every piece carries a material class
     (painted metal, lacquer, brushed steel, chrome, anodised gunmetal, carbon fibre, matte polymer, rubber,
     ballistic nylon, quilted suit, braided cord, gold trim).
  2. High-poly (HP): the game mesh with bevelled hard edges, 2 subdivision levels and floating detail (rivet rows on
     every panel, hinge knuckles), baked onto the game mesh in Cycles (selected-to-active): tangent normal + AO.
     Curvature comes from the baked normal map.
  3. Texture synthesis per texel: class material (albedo / metallic / smoothness), micro-normal (weaves, carbon
     twill, brushed streaks, orange-peel paint, quilting with stitches), panel lines, vents, invented decals
     (glyph strips, glyph serials, hazard chevrons, unit marks), curvature/AO driven edge chipping, scratches and
     cavity grime. Outputs BaseColor (designed colours, Unity tint white), Normal (baked + detail, RNM blend),
     MaskMap (R metallic, G AO, B detail mask, A smoothness) for the Armor and SuitSecondary slots.
"""
import bpy, bmesh, os, sys, math, json, time
from contextlib import contextmanager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
import common as C
import gear, texbake as TB, texstage, studio
from gear import Part, plate, light_strip, tube, rbox, bolt, strap, surface_path, limb_coords
from common import ss, nrm, nrm_rows
import armour as A
from armour import (Kit, build_suit, stock_offset, torso_panels, limb_panels, pauldron, limb_guard, joint_cap, collar, reactor, slab,
                    hex_outline, lamella, hub, strut, cuff, emitter, side_bones, spine_key, Region, finalize, unify_slots, fill_weights,
                    SLOTS, REPLACES, KEEPS)

OUT_DIR = os.path.join(C.CUSTOM_OUT, "Armour")
TEX_DIR = os.path.join(OUT_DIR, "Textures")
THUMB_DIR = os.path.join(C.CUSTOM_OUT, "Thumbs")
PREV_DIR = os.path.join(C.PREVIEWS, "armour3")

CLASSES = ["suit", "quilt", "nylon", "rubber", "paint", "paint2", "lacquer", "lacquer2", "steel", "chrome", "gunmetal", "carbon",
           "polymer", "gold", "cord"]
CI = {n: i for i, n in enumerate(CLASSES)}
HARD = {"paint", "paint2", "lacquer", "lacquer2", "steel", "chrome", "gunmetal", "carbon", "polymer", "gold"}


# ============================================================================= kit with material classes


class Kit3(Kit):
    def __init__(self, ctx, cid):
        super().__init__(ctx, cid)
        self.cls_of = {}
        self.cur = "paint"
        self.panel_ids = set()
        self.free_ids = set()
        self.free = False
        self.facets = 4

    def next_id(self):
        pid = super().next_id()
        self.cls_of[pid] = self.cur
        if self.free:
            self.free_ids.add(pid)
        return pid

    @contextmanager
    def cls(self, name, free=False):
        old, oldf = self.cur, self.free
        self.cur, self.free = name, free or oldf
        try:
            yield
        finally:
            self.cur, self.free = old, oldf

    # ------------------------------------------------------------------ extra pieces
    def webbing(self, key, pts, width=0.038, thick=0.003, push=0.002, n=None, cls="nylon"):
        P_, N_ = surface_path(self.ctx, pts, n or max(12, len(pts) * 6), push=push)
        with self.cls(cls):
            strap(self.P(key), P_, N_, width, thick, mat="SuitSecondary", attrs={"plate": self.next_id(), "wear": 0.2}, caps=True)
        return P_, N_

    def cable(self, key, P_, r=0.0035, cls="rubber", mat="SuitSecondary", sides=8):
        with self.cls(cls):
            tube(self.P(key), np.asarray(P_), r, sides, mat=mat, attrs={"plate": self.next_id(), "wear": 0.3}, caps=True)

    def buckle(self, key, p, t, n, width):
        with self.cls("steel"):
            pid = self.next_id()
            part = self.P(key)
            t = nrm(t); n = nrm(n); s = np.cross(n, t)
            W = width + 0.008; L = 0.024
            for (cx, cy, sx, sy) in ((0, L / 2 - 0.0025, W, 0.005), (0, -L / 2 + 0.0025, W, 0.005), (W / 2 - 0.0025, 0, 0.005, L),
                                     (-W / 2 + 0.0025, 0, 0.005, L)):
                rbox(part, p + s * cx + t * cy + n * 0.004, s, t, n, (sx, sy, 0.004), 0.0012, 1, mat="Armor", attrs={"plate": pid, "wear": 1.0})

    def pouch(self, key, p, n, up, w, h, d):
        with self.cls("nylon"):
            pid = self.next_id()
            gear.pouch(self.ctx, self.P(key), p, n, up, w, h, d, mat="SuitSecondary", plate_id=pid)
            self.cls_of[pid] = "nylon"


def mask_close(ctx, mask, n=2):
    """Morphological closing of a body-vertex mask over the mesh adjacency (fills nipple / navel holes and slivers)."""
    B = ctx.B
    nb = [set() for _ in range(B.nv)]
    for f in B.faces:
        for a in f:
            nb[a].update(f)
    m = mask.copy()
    for _ in range(n):
        m = m | np.array([any(m[k] for k in nb[v]) for v in range(B.nv)])
    for _ in range(n):
        m = m & np.array([all(m[k] for k in nb[v]) for v in range(B.nv)])
    return m | mask


def facet(obj, ctx, mode="smooth", strength=0.4, min_off=0.008, iters=24):
    """Hard-shell forming of a body-shaped panel ("inflate"): outward-only Laplacian smoothing of the outer surface,
    so concavities (cleavage, sternum, navel, muscle grooves) fill in and the panel reads as one sculpted plate while
    never moving towards the body; inner/rim vertices follow their nearest outer vertex; body clearance enforced."""
    me = obj.data
    me.update()
    co = gear.get_co(obj)
    vn = gear.vnormals(obj)
    if len(co) < 12:
        return
    bn = np.zeros_like(co)
    for i, p in enumerate(co):
        hit, n, _, d = ctx.tree.find_nearest(Vector(p), 0.3)
        bn[i] = n if hit is not None else vn[i]
    outer = (vn * bn).sum(1) > 0.0
    oi = np.where(outer)[0]
    if len(oi) < 8:
        return
    pos = {v: t for t, v in enumerate(oi)}
    nb = [[] for _ in oi]
    bdry = np.zeros(len(oi), bool)
    for e in me.edges:
        a, b = e.vertices
        if a in pos and b in pos:
            nb[pos[a]].append(pos[b]); nb[pos[b]].append(pos[a])
        elif (a in pos) != (b in pos):
            bdry[pos[a] if a in pos else pos[b]] = True
    P = co[oi].copy()
    N0 = nrm_rows(vn[oi])
    for it in range(iters):
        avg = np.array([P[n_].mean(0) if n_ else P[t] for t, n_ in enumerate(nb)])
        d = avg - P
        if it < iters // 2:            # first half: free smoothing (removes nipples, navel, muscle relief)
            step = d
        else:                          # second half: outward-only (fills remaining concavities)
            dn = (d * N0).sum(1)
            step = d - N0 * np.minimum(dn, 0.0)[:, None]
        P = P + step * np.where(bdry, 0.25, 0.6)[:, None]
    disp = np.zeros_like(co)
    disp[oi] = P - co[oi]
    kd = KDTree(len(oi))
    for t, i in enumerate(oi):
        kd.insert(Vector(co[i]), t)
    kd.balance()
    for i in np.where(~outer)[0]:
        _, t, _ = kd.find(Vector(co[i]))
        disp[i] = disp[oi[t]]
    new = co + disp
    stree = smooth_body_tree(ctx)
    for i, p in enumerate(new):
        for tree, want in ((stree, min_off if outer[i] else min_off * 0.5), (ctx.tree, 0.0058 if outer[i] else 0.0035)):
            hit, n, _, d = tree.find_nearest(Vector(p), 0.3)
            if hit is not None:
                gap = (Vector(p) - hit).dot(n)
                if gap < want:
                    p = np.array(hit) + np.array(n) * want
        new[i] = p
    gear.set_co(obj, new)


_STREE = {}


def smooth_body_tree(ctx):
    """BVH of a heavily smoothed body (no nipples, navel, muscle grooves): clearance reference for sculpted plates."""
    key = id(ctx)
    if key in _STREE:
        return _STREE[key]
    B = ctx.B
    co = ctx.basis.copy()
    nb = [set() for _ in range(B.nv)]
    for f in B.faces:
        for a in f:
            nb[a].update(f)
    nbl = [list(x) for x in nb]
    for _ in range(25):
        avg = np.array([co[n_].mean(0) for n_ in nbl])
        co = co * 0.4 + avg * 0.6
    _STREE[key] = BVHTree.FromPolygons([Vector(c) for c in co], B.faces)
    return _STREE[key]


def panel3(kit, *a, facets=0, **k):
    a = list(a)
    k.setdefault("bsmooth", 40)
    if len(a) > 1 and isinstance(a[1], np.ndarray) and a[1].dtype == bool:
        a[1] = mask_close(kit.ctx, a[1], 2)
    o = PANEL_V2(kit, *a, **k)
    if o is not None:
        kit.panel_ids.add(kit.pid)
        name = a[0] if a else ""
        hard = kit.cur in ("paint", "paint2", "lacquer", "lacquer2", "polymer", "carbon", "gunmetal")
        off = a[2] if len(a) > 2 else k.get("offset", 0.015)
        off = off if not callable(off) else 0.012
        flat = name.startswith(("chest", "muna", "bust", "back", "senaka", "abs", "lumbar", "camo", "waist"))
        facet(o, kit.ctx, "inflate", 0.0, min_off=max(0.0085, off * 0.75), iters=40 if hard else 12)
    return o


PANEL_V2 = A.panel
A.panel = panel3            # torso_panels / limb_panels in armour.py use the module global


def arm_lame(kit, bone, t0, t1, phi0, phi1, push, thick=0.005, key=None, n_phi=12, flare=0.0, R=0.16):
    """Curved lame (cylinder section) wrapped around a limb: rows of surface points at t0/t1 over phi0..phi1, pushed
    out by `push` (+flare at the lower edge), closed into a bevelled slab. Rigid to `key` (default the bone)."""
    phis = np.linspace(phi0, phi1, n_phi)
    rows = []
    for t, pu in ((t0, push), ((t0 + t1) / 2, push + flare * 0.4), (t1, push + flare)):
        pts, nrs = [], []
        for ph in phis:
            p, n = kit.limb(bone, t, ph, push=pu, R=R)
            pts.append(p); nrs.append(n)
        rows.append((np.array(pts), np.array(nrs)))
    top = np.vstack([r[0] for r in rows])
    nr = np.vstack([r[1] for r in rows])
    bot = top - nr * thick
    m = n_phi
    verts = np.vstack([top, bot])
    nv = len(top)
    faces, uvs = [], []
    L = np.linalg.norm(top[m] - top[0]) + 1e-6
    for r in range(2):
        for i in range(m - 1):
            a, b, c, d = r * m + i, r * m + i + 1, (r + 1) * m + i + 1, (r + 1) * m + i
            faces.append([a, d, c, b])
            uvs.append([(i / m, r / 2), (i / m, (r + 1) / 2), ((i + 1) / m, (r + 1) / 2), ((i + 1) / m, r / 2)])
            faces.append([nv + a, nv + b, nv + c, nv + d])
            uvs.append([(2 + i / m, r / 2), (2 + (i + 1) / m, r / 2), (2 + (i + 1) / m, (r + 1) / 2), (2 + i / m, (r + 1) / 2)])
    ring = [0] + list(range(1, m)) + [m + m - 1, 2 * m + m - 1] + list(range(2 * m + m - 2, 2 * m - 1, -1)) + [m]
    for j in range(len(ring)):
        a, b = ring[j], ring[(j + 1) % len(ring)]
        faces.append([a, b, nv + b, nv + a])
        uvs.append([(4 + j * 0.05, 0), (4 + (j + 1) * 0.05, 0), (4 + (j + 1) * 0.05, 0.02), (4 + j * 0.05, 0.02)])
    f0 = faces[0]
    gn = np.cross(verts[f0[1]] - verts[f0[0]], verts[f0[2]] - verts[f0[0]])
    if np.dot(gn, nr[0]) < 0:
        faces = [f[::-1] for f in faces]
        uvs = [u[::-1] for u in uvs]
    pid = kit.next_id()
    lx = np.concatenate([np.tile(np.linspace(-0.5, 0.5, m), 3)] * 2) * L
    ly = np.concatenate([np.repeat([0.0, -0.5, -1.0], m)] * 2) * np.linalg.norm(top[2 * m] - top[0])
    wear = np.concatenate([np.ones(nv) * 0.0, np.ones(nv)])
    for i in range(nv):
        if i % m in (0, m - 1) or i < m or i >= 2 * m:
            wear[i] = 1.0
    kit.P(key or bone).add(verts, faces, "Armor", uvs, {"plate": np.full(len(verts), float(pid)), "wear": wear, "lx": lx, "ly": ly})
    return top[:m], top[2 * m:]


def waist_ring(kit, key, z0, z1, push, mat="Armor", n=40):
    """Band around the torso between heights z0 > z1 (arm-aware casts), closed loop of quads with a rim."""
    rows = []
    for zz in (z0, z1):
        rows.append([kit.torso(zz, -math.pi + 2 * math.pi * k / n, push=push, R=0.4) for k in range(n)])
    verts, faces = [], []
    for r in rows:
        verts += [p for p, _ in r]
    outer = np.array(verts)
    nrs = np.array([nn for r in rows for _, nn in r])
    inner = outer - nrs * 0.004
    V = np.vstack([outer, inner])
    m = 2 * n
    for k in range(n):
        k2 = (k + 1) % n
        faces.append([k, k2, n + k2, n + k])
        faces.append([m + k, m + n + k, m + n + k2, m + k2])
        faces.append([k2, k, m + k, m + k2])
        faces.append([n + k, n + k2, m + n + k2, m + n + k])
    f0 = faces[0]
    gn = np.cross(V[f0[1]] - V[f0[0]], V[f0[2]] - V[f0[0]])
    if np.dot(gn, nrs[0]) < 0:
        faces = [f[::-1] for f in faces]
    pid = kit.next_id()
    kit.P(key).add(V, faces, mat, None, {"plate": np.full(len(V), float(pid)), "wear": np.full(len(V), 0.4)})


def ring_path(kit, bone, t, phis, push):
    return np.array([kit.limb(bone, t, ph, push=push)[0] for ph in phis])


# ============================================================================= sets


def set_vanguard_mk2(kit):
    """Tactical plate carrier: ballistic-nylon carrier (front/back plates, cummerbund, padded shoulder straps, MOLLE
    rows, magazine/admin/radio pouches), chest reactor, power pack, heavy layered pauldrons, armoured limbs."""
    ctx, L = kit.ctx, kit.L
    with kit.cls("suit"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.002))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    tor = (rg.R["torso"] + rg.R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    with kit.cls("nylon"):
        panel3(kit, "carrier_f", tor & front & (z > hips + 0.07) & (z < nk - 0.06) & (np.abs(x) < 0.155), 0.026, rim=0.014, mat="SuitSecondary")
        panel3(kit, "carrier_b", tor & ~front & (z > hips + 0.07) & (z < nk - 0.05) & (np.abs(x) < 0.15), 0.024, rim=0.014, mat="SuitSecondary")
        for s_ in (1, -1):   # cummerbund
            panel3(kit, f"cumm{s_}", tor & (z > hips + 0.06) & (z < sp1 + 0.02) & (np.abs(x) > 0.11) & (x * s_ > 0), 0.018, rim=0.008,
                   mat="SuitSecondary")
    # padded shoulder straps
    for s_ in (1, -1):
        f = kit.torso(nk - 0.07, s_ * 0.45, push=0.03)[0]
        b = kit.torso(nk - 0.07, math.pi - s_ * 0.45, push=0.03)[0]
        top = L["LeftShoulder" if s_ > 0 else "RightShoulder"] + np.array((s_ * 0.0, 0.0, 0.06))
        kit.webbing("Spine2", [f, (f + top) / 2 + np.array((0, 0, 0.02)), top, (top + b) / 2 + np.array((0, 0, 0.02)), b], width=0.05,
                    thick=0.008, push=0.012)
    # MOLLE rows on the front carrier
    for r in range(3):
        zr = hips + 0.11 + r * 0.035
        for k in range(-3, 3):
            x0 = k * 0.042 + 0.006
            pts = [kit.torso(zr, math.atan2(xx, 0.12) * 1.0, push=0.032)[0] for xx in (x0, x0 + 0.03)]
            kit.webbing("Spine1", pts, width=0.025, thick=0.0035, push=0.0, n=4)
    # pouches: 3 magazine pouches low front, admin pouch on the chest, radio pouch on the left side
    for k in (-1, 0, 1):
        p, n = kit.torso(hips + 0.12, k * 0.3, push=0.034)
        kit.pouch("Spine", p, n, (0, 0, 1), 0.06, 0.1, 0.03)
    p, n = kit.torso(sp2 + 0.0, 0.25, push=0.034)
    kit.pouch("Spine2", p, n, (0, 0, 1), 0.09, 0.07, 0.022)
    p, n = kit.torso(sp1 - 0.01, 1.35, push=0.024, R=0.2)
    kit.pouch("Spine1", p, n, (0, 0, 1), 0.05, 0.11, 0.035)
    # reactor on the upper chest with a polymer housing
    p, n = kit.torso(nk - 0.11, 0.0)
    with kit.cls("gunmetal"):
        reactor(kit, "Spine2", p + n * 0.05, n, (0, 0, 1), 0.03)
    # power pack
    p, n = kit.torso(sp2 - 0.01, math.pi, R=0.4)
    with kit.cls("gunmetal"):
        r_, u_, n_ = kit.box("Spine2", p + n * 0.055, n, (0, 0, 1), (0.15, 0.19, 0.05), 0.008)
        for s_ in (1, -1):
            c = p + n * 0.055 + r_ * s_ * 0.09
            tube(kit.P("Spine2"), np.array([c + u_ * 0.06, c - u_ * 0.075]), 0.018, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0},
                 caps=True)
    with kit.cls("steel"):
        for k in range(4):
            kit.box("Spine2", p + n * 0.082 + u_ * (0.055 - k * 0.03), n, (0, 0, 1), (0.11, 0.008, 0.004), 0.001, mat="Armor")
    for k in range(3):
        kit.box("Spine2", p + n * 0.0815 + u_ * (0.04 - k * 0.03), n, (0, 0, 1), (0.08, 0.003, 0.003), 0.0008, mat="Glow")
    for s_ in (1, -1):
        c = p + n * 0.055 + r_ * s_ * 0.09
        tube(kit.P("Spine2"), np.array([c + u_ * 0.04 + n_ * 0.016, c - u_ * 0.055 + n_ * 0.016]), 0.0045, 8, mat="Glow2")
    # limbs
    with kit.cls("paint"):
        for s_ in (1, -1):
            limb_panels(kit, rg, s_, arm_off=0.018, leg_off=0.02, cover=0.6)
            bu, bf, bt, bs, bh = side_bones(s_)
            pauldron(kit, s_, 1.15, layers=3, offset=0.032)
            joint_cap(kit, bu, bf, (s_ * 0.5, 0.6, -0.2), 0.032, 0.022)
            joint_cap(kit, bt, bs, (0, -1, 0.05), 0.046, 0.026)
            for k, ph in enumerate((0.35, 1.0)):
                p, n = kit.torso(hips - 0.075, s_ * ph, R=0.19)
                kit.plate(bt, p, n, (0, 0, 1), 0.066 if k == 0 else 0.05, 0.068, offset=0.028, thickness=0.007, crown=0.005, chamfer=0.003,
                          n_exp=4.0, segs=28, groove=0.62, poly=[(-1, 1), (1, 1), (0.85, -0.7), (0.4, -1), (-0.4, -1), (-0.85, -0.7)], corner=0.2)
    with kit.cls("paint2"):
        for s_ in (1, -1):
            bu, bf, bt, bs, bh = side_bones(s_)
            limb_guard(kit, bf, 0.55, 0.92, math.radians(-25), 0.03, offset=0.03, groove=0.0, n_exp=6, segs=20)
    with kit.cls("gunmetal"):
        waist_ring(kit, "Hips", hips + 0.03, hips - 0.02, 0.022)
    for s_ in (1, -1):
        kit.strip("suit", [kit.limb(side_bones(s_)[1], t, math.radians(150 * s_), push=0.0)[0] for t in np.linspace(0.1, 0.9, 7)], mat="Glow2")
    collar_soft(kit, 0.024)
    return suit


def collar_soft(kit, push):
    """Padded nylon collar ring around the neck base."""
    L = kit.L
    nk = L["Neck"]
    with kit.cls("nylon"):
        for r in range(2):
            z = nk[2] - 0.03 + r * 0.02
            pts = []
            for k in range(25):
                ph = -math.pi + 2 * math.pi * k / 24
                d = np.array((math.sin(ph), -math.cos(ph), 0.0))
                c0 = np.array((0.0, nk[1] + 0.005, z))
                hit, n = kit.ctx.cast(c0 + d * 0.25, -d, 0.3)
                pts.append((hit if hit is not None else c0 + d * 0.07) + d * (push + 0.006 * r))
            P_ = np.array(pts)
            tube(kit.P(("Neck", "Spine2")), P_, 0.011 - 0.003 * r, 10, mat="SuitSecondary", attrs={"plate": kit.next_id(), "wear": 0.2})


def piston(kit, key, a, b, r=0.007):
    """Hydraulic piston: anodised cylinder + chrome rod + glowing seal ring."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = a + (b - a) * 0.55
    with kit.cls("gunmetal"):
        tube(kit.P(key), np.array([a, m]), r, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.8}, caps=True)
    with kit.cls("chrome"):
        tube(kit.P(key), np.array([m - (b - a) * 0.02, b]), r * 0.55, 10, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.2}, caps=True)
    tube(kit.P(key), np.array([m - (b - a) * 0.01, m + (b - a) * 0.015]), r * 1.12, 12, mat="Glow2", caps=True)


def set_aegis_exo(kit):
    """Exoskeleton frame over quilted techwear: brushed-steel spine column and shoulder yoke, carbon-fibre plates,
    actuator hubs, struts with hydraulic pistons along every limb, cable runs, waist ring and cuffs."""
    ctx, L = kit.ctx, kit.L
    with kit.cls("suit"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.0065, 0.004))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    with kit.cls("paint"):
        # machined pectoral plates + sternum plate (crisp outlines, chamfered metal edges, bolts)
        for s_ in (1, -1):
            p, n = kit.torso((sp2 + nk) * 0.5 - 0.005, s_ * 0.42, R=0.4)
            kit.plate("Spine2", p, nrm(n + np.array((0, 0, 0.12))), (0, 0, 1), 0.092, 0.078, offset=0.012, thickness=0.008, crown=0.01,
                      chamfer=0.0035, groove=0.68, groove_depth=0.0016, ridge=0.002, gasket="SuitSecondary", segs=40,
                      poly=[(-1, 0.6), (-0.7, 1), (0.9, 1), (1, 0.4), (0.85, -0.6), (0.4, -1), (-0.8, -1), (-1, -0.4)] if s_ > 0 else
                      [(1, 0.6), (0.7, 1), (-0.9, 1), (-1, 0.4), (-0.85, -0.6), (-0.4, -1), (0.8, -1), (1, -0.4)], corner=0.18,
                      bolts=[(-0.7 * s_, 0.75), (0.75 * s_, -0.7), (0.6 * s_, 0.6)])
        for r in range(3):
            zr = sp1 - 0.025 - r * 0.05
            for s_ in (1, -1):
                p, n = kit.torso(zr, s_ * 0.19, R=0.4)
                kit.plate("Spine1" if r == 0 else "Spine", p, n, (0, 0, 1), 0.045, 0.021, offset=0.008, thickness=0.006, crown=0.003,
                          chamfer=0.0025, n_exp=5.0, segs=28, groove=0.0, bolts=[(-0.8 * s_, 0.0)])
    with kit.cls("carbon"):
        for s_ in (1, -1):
            limb_panels(kit, rg, s_, arm_off=0.016, leg_off=0.017, upper=False, thigh=False, cover=0.45)
    with kit.cls("gunmetal"):
        for k, zz in enumerate(np.linspace(hips + 0.02, nk - 0.01, 9)):
            p, n = kit.torso(zz, math.pi, push=0.004, R=0.4)
            kit.box(spine_key(kit, zz), p + n * 0.016, n, (0, 0, 1), (0.058 - 0.004 * (k % 2), 0.03, 0.026), 0.005)
    for zz in np.linspace(hips + 0.02, nk - 0.01, 9):
        p, n = kit.torso(zz, math.pi, push=0.004, R=0.4)
        kit.box(spine_key(kit, zz), p + n * 0.0295, n, (0, 0, 1), (0.02, 0.012, 0.002), 0.0008, mat="Glow")
    spine = np.array([kit.torso(zz, math.pi, push=0.036)[0] for zz in np.linspace(hips + 0.02, nk - 0.01, 14)])
    with kit.cls("steel"):
        for dx in (0.02, -0.02):
            tube(kit.P("Spine2"), spine + np.array((dx, 0, 0)), 0.006, 10, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        sh = L[bu]
        yoke = [kit.torso(sp2 + 0.04, math.pi - s_ * 0.25, push=0.032)[0], sh + np.array((-s_ * 0.06, 0.04, 0.088)),
                sh + np.array((-s_ * 0.05, -0.055, 0.072)), kit.torso(sp2 + 0.06, s_ * 0.45, push=0.03)[0]]
        with kit.cls("steel"):
            tube(kit.P("Spine2"), np.array(gear.catmull(yoke, 18)), 0.014, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
        with kit.cls("gunmetal"):
            d = nrm(np.array((s_ * 1.0, 0, 0.25)))
            hub(kit, bu, sh + d * 0.088, d, (0, 0, 1), 0.038)
            hub(kit, bf, L[bf] + nrm(np.array((s_ * 0.6, 0.6, 0.0))) * 0.06, nrm(np.array((s_ * 0.6, 0.6, 0.0))), (0, 0, 1), 0.028)
            hub(kit, "Hips", L[bt] + np.array((s_ * 0.118, 0.0, 0.0)), np.array((s_ * 1.0, 0, 0)), (0, 0, 1), 0.042)
            hub(kit, bs, L[bs] + np.array((s_ * 0.08, 0.0, 0.0)), np.array((s_ * 1.0, 0, 0)), (0, 0, 1), 0.034)
        with kit.cls("steel"):
            for (bone, t0, t1, ph, pu, rr) in ((bu, 0.15, 0.85, -100 * s_, 0.032, 0.015), (bf, 0.08, 0.86, -115 * s_, 0.03, 0.013),
                                               (bt, 0.1, 0.86, (-90 if s_ > 0 else 90), 0.036, 0.018), (bs, 0.08, 0.74, (-90 if s_ > 0 else 90), 0.034, 0.015)):
                strut(kit, bone, bone, t0, t1, math.radians(ph), push=pu, r=rr, piston=False)
                for tt in (t0 + 0.06, t1 - 0.06):
                    q, qn = kit.limb(bone, tt, math.radians(ph), push=pu)
                    tube(kit.P(bone), np.array([q - qn * rr * 1.2, q + qn * rr * 1.2]), rr * 1.35, 12, mat="Armor",
                         attrs={"plate": kit.next_id(), "wear": 1.0}, caps=True)
        # pistons alongside the struts
        for bone, t0, t1, ph, pu in ((bu, 0.2, 0.75, -125 * s_, 0.024), (bf, 0.12, 0.7, -140 * s_, 0.022),
                                     (bt, 0.15, 0.75, (-115 if s_ > 0 else 115), 0.026), (bs, 0.12, 0.6, (-115 if s_ > 0 else 115), 0.024)):
            a = kit.limb(bone, t0, math.radians(ph), push=pu)[0]; b = kit.limb(bone, t1, math.radians(ph), push=pu)[0]
            piston(kit, bone, a, b, 0.0075)
        with kit.cls("gunmetal"):
            cuff(kit, bf, bf, 0.9, 0.012, 0.026)
            cuff(kit, bs, bs, 0.76, 0.014, 0.028)
        with kit.cls("paint2"):
            joint_cap(kit, bt, bs, (0, -1, 0.05), 0.04, 0.022)
            pauldron(kit, s_, 0.8, layers=1, offset=0.026)
        # cable run from the spine to the shoulder hub
        a = kit.torso(sp2 + 0.03, math.pi - s_ * 0.2, push=0.03)[0]
        b = sh + nrm(np.array((s_ * 1.0, 0, 0.25))) * 0.07 + np.array((0, 0.02, 0.0))
        kit.cable("Spine2", np.array(gear.catmull([a, (a + b) / 2 + np.array((0, 0.03, 0.03)), b], 14)), 0.004)
    with kit.cls("gunmetal"):
        waist_ring(kit, "Hips", hips + 0.016, hips - 0.028, 0.022)
        p, n = kit.torso(sp2 - 0.0, 0.0)
        kit.box("Spine2", p + n * 0.04, n, (0, 0, 1), (0.06, 0.07, 0.014), 0.004)
    kit.box("Spine2", p + n * 0.048, n, (0, 0, 1), (0.046, 0.054, 0.002), 0.001, mat="Screen")
    with kit.cls("steel"):
        collar(kit, rows=1, height=0.028, push=0.016, segs=8)
    return suit


def set_phantom_stealth(kit):
    """Matte stealth: layered fabric (base suit + overlay wraps with seams), hexagonal matte polymer plates with
    light-bending cells, low-profile shoulder plates, thin glow seams, stealth collar."""
    ctx, L = kit.ctx, kit.L
    female = kit.cid == "lyra"
    with kit.cls("quilt"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.0038, 0.001))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    R = rg.R
    tor = (R["torso"] + R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    with kit.cls("nylon"):   # overlay fabric wraps
        diag = (z - (sp1 - 0.02)) + 0.5 * x
        panel3(kit, "wrap_a", tor & (diag < 0.0) & (z > hips - 0.04) & (np.abs(x) < 0.2), 0.0085, rim=0.003, mat="SuitSecondary")
        for s_ in (1, -1):
            t, phi, r = rg.limb(side_bones(s_)[2])
            panel3(kit, f"wrap_t{s_}", (R["thighL" if s_ > 0 else "thighR"] > 0.5) & (t > 0.1) & (t < 0.6), 0.008, rim=0.003, mat="SuitSecondary")
            t, phi, r = rg.limb(side_bones(s_)[1])
            panel3(kit, f"wrap_f{s_}", (R["farmL" if s_ > 0 else "farmR"] > 0.5) & (t > 0.35) & (t < 0.95), 0.008, rim=0.003, mat="SuitSecondary")
    with kit.cls("polymer"):
        for s_ in (1, -1):
            d2 = (z - (sp1 + 0.02)) - 0.6 * (np.abs(x) - 0.05)
            panel3(kit, f"camo_chest{s_}", tor & front & (x * s_ > 0.01) & (d2 > 0.0) & (z < nk - 0.05) & (np.abs(x) < 0.17), 0.015, rim=0.005)
            panel3(kit, f"camo_back{s_}", tor & ~front & (x * s_ > 0.014) & (z > sp1 - 0.05) & (z < nk - 0.05) & (np.abs(x) < 0.15), 0.014,
                   rim=0.005)
            limb_panels(kit, rg, s_, arm_off=0.013, leg_off=0.014, cover=0.42, upper=True, thigh=True)
            bu, bf, bt, bs, bh = side_bones(s_)
            pauldron(kit, s_, 0.72 if not female else 0.62, layers=2, offset=0.016)
            joint_cap(kit, bt, bs, (0, -1, 0.05), 0.034, 0.016, groove=0.0)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        kit.strip("suit", [kit.torso(z_, s_ * 1.42, push=0.0)[0] for z_ in np.linspace(hips - 0.02, sp2 - 0.03, 8)])
        kit.strip("suit", [kit.limb(bt, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.62, 0.95, 4)] +
                  [kit.limb(bs, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.05, 0.75, 6)])
    A.seam_strips(kit, "Glow2")
    with kit.cls("polymer"):
        collar(kit, rows=2, height=0.022, push=0.012, segs=10)
    return suit


def lace_column(kit, key, pts_top, pts_bot, r=0.0016):
    """Cross lacing (odoshi) between two rows of points: X pattern of braided cords."""
    for (a, b), (c, d) in zip(zip(pts_top[:-1], pts_top[1:]), zip(pts_bot[:-1], pts_bot[1:])):
        kit.cable(key, np.array([a, (a + d) / 2, d]), r, cls="cord", mat="SuitSecondary", sides=6)
        kit.cable(key, np.array([b, (b + c) / 2, c]), r, cls="cord", mat="SuitSecondary", sides=6)


def set_samurai_neo(kit):
    """Cyber-samurai: deep red lacquered lamellar do laced with braided cords, black-lacquer muna-ita with gold trim
    and a reactor crest, layered sode laced to the upper arms, kusazuri skirt lames, kote and suneate."""
    ctx, L = kit.ctx, kit.L
    with kit.cls("suit"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.002))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    tor = (rg.R["torso"] + rg.R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    with kit.cls("lacquer"):
        panel3(kit, "muna", tor & front & (z > sp2 - 0.0) & (z < nk - 0.04) & (np.abs(x) < 0.17), 0.03, rim=0.008)
        panel3(kit, "senaka", tor & ~front & (z > sp2 - 0.03) & (z < nk - 0.04) & (np.abs(x) < 0.16), 0.026, rim=0.007)
    # gold trim along the muna-ita lower edge
    with kit.cls("gold"):
        tr = np.array([kit.torso(sp2 + 0.002, ph, push=0.034)[0] for ph in np.linspace(-0.95, 0.95, 14)])
        tube(kit.P("Spine2"), tr, 0.0035, 8, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0}, caps=True)
    rows = np.linspace(hips + 0.035, sp2 - 0.02, 4)
    prev = None
    for r, zr in enumerate(rows):
        key = spine_key(kit, zr)
        phs = [-1.25 + 2.5 * (k + 0.5 * (r % 2)) / 8 for k in range(8)]
        with kit.cls("lacquer"):
            for ph in phs:
                p, n = kit.torso(zr, ph)
                lamella(kit, key, p, n, (0, 0, 1), 0.024, 0.029, off=0.008 + 0.004 * r)
            for k in range(4):
                ph = math.pi - 0.75 + 1.5 * (k + 0.5 * (r % 2)) / 4
                p, n = kit.torso(zr, ph)
                lamella(kit, key, p, n, (0, 0, 1), 0.032, 0.029, off=0.008 + 0.004 * r)
        top = [kit.torso(zr + 0.022, ph, push=0.015 + 0.004 * r)[0] for ph in np.linspace(-1.25, 1.25, 10)]
        if prev is not None:
            lace_column(kit, key, prev, top)
        prev = [kit.torso(zr - 0.022, ph, push=0.015 + 0.004 * r)[0] for ph in np.linspace(-1.25, 1.25, 10)]
        kit.strip(key, [kit.torso(zr + 0.027, ph, push=0.017 + 0.004 * r)[0] for ph in np.linspace(-1.3, 1.3, 10)], push=0.0, width=0.0022)
    p, n = kit.torso(sp2 + 0.05, 0.0)
    with kit.cls("gold"):
        reactor(kit, "Spine2", p + n * 0.046, n, (0, 0, 1), 0.024)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        # sode: four wide laced lames on the outer upper arm
        lam_rows = []
        c0 = math.radians(-95 * s_)
        for j in range(5):
            t0 = 0.02 + 0.13 * j
            with kit.cls("lacquer" if j % 2 == 0 else "lacquer2"):
                topr, botr = arm_lame(kit, bu, t0, t0 + 0.15, c0 - math.radians(62), c0 + math.radians(62), 0.03 + 0.007 * (4 - j),
                                      thick=0.005, flare=0.012, n_phi=10)
            lam_rows.append(topr[::2] + 0.0)
        for j in range(4):
            lace_column(kit, bu, lam_rows[j] + 0.004, lam_rows[j + 1] + 0.004)
        with kit.cls("lacquer2"):
            pauldron(kit, s_, 0.95, layers=1, offset=0.024)
        with kit.cls("lacquer"):
            limb_panels(kit, rg, s_, arm_off=0.015, leg_off=0.017, upper=False, thigh=True, cover=0.5)
        with kit.cls("gold"):
            cuff(kit, bf, bf, 0.93, 0.012, 0.016)
        for ph in (0.38, 0.95):
            ks = []
            for r in range(3):
                zz = hips - 0.035 - r * 0.05
                p, n = kit.torso(zz, s_ * ph, R=0.19)
                with kit.cls("lacquer"):
                    lamella(kit, bt, p, n, (0, 0, 1), 0.056, 0.025, off=0.024 + 0.005 * (2 - r), segs=16)
                ks.append([p + n * (0.03 + 0.005 * (2 - r)) + np.array((0, 0, 0.018)) + np.array((dx, 0, 0)) for dx in (-0.03, 0.0, 0.03)])
            for r in range(2):
                lace_column(kit, bt, ks[r], ks[r + 1])
        with kit.cls("lacquer2"):
            joint_cap(kit, bt, bs, (0, -1, 0.05), 0.04, 0.024)
    for r in range(3):
        for k in range(3):
            p, n = kit.torso(hips - 0.03 - r * 0.048, math.pi + (k - 1) * 0.42, R=0.19)
            with kit.cls("lacquer"):
                lamella(kit, "Hips", p, n, (0, 0, 1), 0.055, 0.025, off=0.024 + 0.005 * (2 - r), segs=16)
    with kit.cls("lacquer2"):
        collar(kit, rows=1, height=0.032, push=0.02, segs=10)
    return suit


def set_netrunner_x(kit):
    """Cable-laced harness: pearl polymer plates on a black bodysuit, nylon harness (X across the chest, shoulder
    straps, belt) with braided data cables laced through it, a chest data hub, spine cable bundle and ports."""
    ctx, L = kit.ctx, kit.L
    with kit.cls("suit"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.0036, 0.0008))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    with kit.cls("polymer"):
        torso_panels(kit, rg, off=0.013, gap=0.009, rows_abs=2, back=False, female=True)
        for s_ in (1, -1):
            limb_panels(kit, rg, s_, arm_off=0.011, leg_off=0.013, upper=False, thigh=False, cover=0.5)
            bu, bf, bt, bs, bh = side_bones(s_)
            pauldron(kit, s_, 0.62, layers=2, offset=0.012)
            joint_cap(kit, bt, bs, (0, -1, 0.05), 0.03, 0.014)
    # harness: X across the chest, over the shoulders, belt
    hub_c = kit.torso(sp2 - 0.02, 0.0, push=0.036)[0]
    for s_ in (1, -1):
        sh_f = kit.torso(nk - 0.05, s_ * 0.55, push=0.022)[0]
        sh_top = L["LeftShoulder" if s_ > 0 else "RightShoulder"] + np.array((s_ * 0.01, 0.0, 0.055))
        sh_b = kit.torso(nk - 0.05, math.pi - s_ * 0.55, push=0.02)[0]
        hip_f = kit.torso(hips + 0.05, -s_ * 0.5, push=0.02)[0]
        hip_b = kit.torso(hips + 0.05, math.pi + s_ * 0.5, push=0.02)[0]
        P1, N1 = kit.webbing("Spine2", [sh_f, hub_c, hip_f], width=0.032, thick=0.004, push=0.026)
        kit.webbing("Spine2", [sh_f, (sh_f + sh_top) / 2 + np.array((0, 0, 0.02)), sh_top, sh_b], width=0.032, thick=0.004, push=0.026)
        P2, N2 = kit.webbing("Spine2", [sh_b, kit.torso(sp1, math.pi, push=0.02)[0], hip_b], width=0.03, thick=0.004, push=0.02)
        for Pp, Nn in ((P1, N1), (P2, N2)):
            Tt = gear.tangents(Pp)
            Ss = nrm_rows(np.cross(Nn, Tt))
            zig = Pp + Nn * 0.006 + Ss * (0.011 * np.sin(np.arange(len(Pp)) * 1.3))[:, None]
            kit.cable("Spine2", zig, 0.0028, cls="cord")
            kit.cable("Spine2", Pp + Nn * 0.008 - Ss * 0.009, 0.0022, cls="rubber")
    with kit.cls("nylon"):
        waist_ring(kit, "Hips", hips + 0.035, hips + 0.008, 0.012, mat="SuitSecondary")
    with kit.cls("gunmetal"):
        r_, u_, n_ = kit.box("Spine2", hub_c + nrm(hub_c - np.array((0, L["Spine1"][1], hub_c[2]))) * 0.012, np.array((0, -1.0, 0.1)), (0, 0, 1),
                             (0.05, 0.05, 0.016), 0.005)
    kit.box("Spine2", hub_c + np.array((0, -0.03, 0.0)), np.array((0, -1.0, 0.1)), (0, 0, 1), (0.034, 0.034, 0.002), 0.001, mat="Screen")
    # spine cable bundle
    zs = np.linspace(nk + 0.02, hips + 0.03, 16)
    base = np.array([kit.torso(zz, math.pi, push=0.0)[0] for zz in zs])
    nrms = np.array([kit.torso(zz, math.pi, push=0.0)[1] for zz in zs])
    for k, dx in enumerate((-0.014, -0.007, 0.0, 0.007, 0.014)):
        P_ = base + nrms * (0.014 + 0.003 * (k % 2)) + np.array((dx, 0, 0)) * (1 + 0.5 * np.sin(np.linspace(0, math.pi, len(zs))))[:, None]
        if k == 2:
            tube(kit.P("suit"), np.array(gear.catmull(list(P_), 40)), 0.0046, 8, mat="Glow")
        else:
            kit.cable("suit", np.array(gear.catmull(list(P_), 40)), 0.0036, cls="cord" if k % 2 else "rubber")
    with kit.cls("gunmetal"):
        for zz in np.linspace(nk - 0.04, hips + 0.06, 6):
            p, n = kit.torso(zz, math.pi, push=0.004)
            kit.box(spine_key(kit, zz), p + n * 0.015, n, (0, 0, 1), (0.046, 0.014, 0.014), 0.003)
        p, n = kit.torso(nk - 0.01, math.pi, push=0.004)
        kit.box("Spine2", p + n * 0.017, n, (0, 0, 1), (0.056, 0.038, 0.02), 0.004)
    kit.box("Spine2", p + n * 0.0275, n, (0, 0, 1), (0.04, 0.022, 0.002), 0.0008, mat="Screen")
    with kit.cls("polymer"):
        p, n = kit.limb("LeftForeArm", 0.55, math.radians(-30), push=0.024)
        axf = nrm(L["LeftHand"] - L["LeftForeArm"])
        kit.box("LeftForeArm", p, n, axf, (0.032, 0.07, 0.008), 0.003)
    kit.box("LeftForeArm", p + n * 0.0045, n, axf, (0.026, 0.058, 0.002), 0.0008, mat="Screen")
    for s_ in (1, -1):
        bt, bs = side_bones(s_)[2:4]
        kit.strip("suit", [kit.limb(bt, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.08, 0.95, 7)] +
                  [kit.limb(bs, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.05, 0.75, 6)], mat="Glow2")
    with kit.cls("polymer"):
        collar(kit, rows=1, height=0.024, push=0.01, segs=10)
    return suit


def wing(kit, key, base, out, up, back, n_blades=5, length=0.2, side=1):
    """Winged pauldron: a fan of layered feather blades rising from the shoulder cap (bevelled prisms, gold edges)."""
    for j in range(n_blades):
        a = (j - (n_blades - 1) / 2) / max(n_blades - 1, 1)          # -0.5 .. 0.5
        dirv = nrm(up * (1.0 - 0.3 * abs(a)) + back * (0.65 + 0.7 * a) + out * (0.55 - 0.3 * a))
        L_ = length * (1.0 - 0.28 * abs(a) * 2)
        o = base + back * (0.012 * j) + out * (0.006 * j)
        rr = nrm(np.cross(dirv, out))
        nn_ = nrm(np.cross(rr, dirv))
        pts = [(-0.012, 0.0), (0.014, 0.0), (0.022, L_ * 0.55), (0.004, L_), (-0.01, L_ * 0.62)]
        with kit.cls("paint" if j % 2 == 0 else "steel", free=True):
            slab(kit, key, pts, o, rr * side, dirv, nn_, 0.0045)
        with kit.cls("gold", free=True):
            tube(kit.P(key), np.array([o + dirv * 0.01 + rr * side * 0.015, o + dirv * L_ * 0.55 + rr * side * 0.023, o + dirv * (L_ * 0.97)]) +
                 nn_ * 0.0025, 0.0016, 6, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0})


def set_valkyrie(kit):
    """Elegant segmented armour: silver enamel bust plate and waist segments with gold trim, winged pauldrons
    (layered feather blades), long tassets, pointed knee guards, flared vambraces and greaves."""
    ctx, L = kit.ctx, kit.L
    with kit.cls("quilt"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.004, 0.001))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    tor = (rg.R["torso"] + rg.R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    with kit.cls("paint"):
        panel3(kit, "bust", tor & front & (z > sp1 + 0.035) & (z < nk - 0.05) & (np.abs(x) < 0.15), 0.016, rim=0.006)
        for r in range(3):
            z1 = sp1 + 0.0 - r * 0.045
            panel3(kit, f"waist{r}", tor & (z > z1 - 0.045) & (z < z1) & (front | (np.abs(x) > 0.08)) & (np.abs(x) < 0.16), 0.012 + 0.004 * (2 - r),
                   rim=0.005)
            kit.strip("suit", [kit.torso(z1 - 0.038, ph, push=0.0)[0] for ph in np.linspace(-1.2, 1.2, 9)], mat="Glow", width=0.003)
        panel3(kit, "backplate", tor & ~front & (z > sp1 - 0.02) & (z < nk - 0.05) & (np.abs(x) < 0.14), 0.014, rim=0.006)
    with kit.cls("gold"):
        tr = np.array([kit.torso(nk - 0.052, ph, push=0.022)[0] for ph in np.linspace(-0.9, 0.9, 12)])
        tube(kit.P("Spine2"), tr, 0.0028, 8, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0}, caps=True)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        with kit.cls("paint"):
            sh = pauldron(kit, s_, 0.86, layers=2, offset=0.016,
                          poly=[(-1, 0.3), (-0.3, 1), (0.8, 0.9), (1, 0.2), (0.8, -0.8), (0.2, -1), (-0.6, -0.9), (-1, -0.4)])
        base = sh + np.array((s_ * 0.06, 0.03, 0.095))
        wing(kit, bu, base, nrm(np.array((s_ * 1.0, 0.0, 0.15))), np.array((0, 0, 1.0)), np.array((0, 1.0, 0.0)), n_blades=6, length=0.3, side=s_)
        with kit.cls("paint"):
            limb_panels(kit, rg, s_, arm_off=0.012, leg_off=0.014, cover=0.55)
            joint_cap(kit, bu, bf, (s_ * 0.5, 0.6, -0.2), 0.024, 0.016)
            for ph, ln in ((0.42, 0.1), (1.15, 0.085)):
                p, n = kit.torso(hips - 0.095, s_ * ph, R=0.19)
                kit.plate(bt, p, n, (0, 0, 1), 0.048, ln, offset=0.022, thickness=0.005, crown=0.004, chamfer=0.0025, groove=0.64, segs=28,
                          poly=[(-1, 1), (1, 1), (0.8, -0.6), (0, -1), (-0.8, -0.6)], corner=0.12)
            kn = L[bs]
            hit, nn = ctx.cast(kn + np.array((0, -0.2, 0.0)), (0, 1, 0), 0.3)
            kit.plate(bs, hit, nrm(nn), (0, 0, 1), 0.04, 0.065, mode="radial", pivot=kn, offset=0.022, thickness=0.006, crown=0.008, chamfer=0.003,
                      groove=0.0, segs=28, poly=[(-1, 0.4), (0, 1), (1, 0.4), (0.8, -0.8), (0, -1), (-0.8, -0.8)], corner=0.1, cast_r=0.14)
    p, n = kit.torso(sp2 + 0.065, 0.0)
    with kit.cls("gold"):
        hub(kit, "Spine2", p + n * 0.024, n, (0, 0, 1), 0.013, glow="Glow2")
        collar(kit, rows=1, height=0.024, push=0.012, segs=10)
    return suit


def shoulder_emitter(kit, side):
    """Heavy shoulder emitter: anodised housing on a yoke over the shoulder, three coil rings, a glowing projector
    lens, cooling fins and a cable to the back frame."""
    L = kit.L
    bu = "LeftArm" if side > 0 else "RightArm"
    sh = L["LeftArm" if side > 0 else "RightArm"]
    c = sh + np.array((side * 0.035, 0.025, 0.1))
    ax = nrm(np.array((side * 0.12, -1.0, 0.18)))
    key = ("Spine2", bu, "LeftShoulder" if side > 0 else "RightShoulder")
    with kit.cls("gunmetal", free=True):
        tube(kit.P(key), np.array([c - ax * 0.08, c + ax * 0.07]), 0.044, 16, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.8}, caps=True)
        tube(kit.P(key), np.array([c - ax * 0.085, c - ax * 0.065]), 0.028, 14, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.8}, caps=True)
    with kit.cls("steel", free=True):
        for k in range(3):
            q = c + ax * (-0.035 + 0.03 * k)
            tube(kit.P(key), np.array([q - ax * 0.007, q + ax * 0.007]), 0.051, 18, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0},
                 caps=True)
    with kit.cls("paint2", free=True):
        rr = nrm(np.cross(ax, (0, 0, 1.0)))
        for k in range(4):
            fpos = c + ax * (-0.055 + 0.028 * k) + np.array((0, 0, 0.05))
            kit.box(key, fpos, np.array((0, 0, 1.0)), ax, (0.004, 0.022, 0.03), 0.001)
    tube(kit.P(key), np.array([c + ax * 0.068, c + ax * 0.076]), 0.033, 16, mat="Glow", caps=True)
    with kit.cls("gunmetal", free=True):
        # yoke down onto the shoulder
        tube(kit.P(key), np.array([c - np.array((0, 0, 0.035)), sh + np.array((-side * 0.03, 0.01, 0.05))]), 0.014, 10, mat="Armor",
             attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
    back = kit.torso(L["Spine2"][2] + 0.04, math.pi - side * 0.4, push=0.04)[0]
    kit.cable(key, np.array(gear.catmull([c - ax * 0.07, c - ax * 0.12 + np.array((0, 0, -0.01)), back], 14)), 0.005)


def set_arc_sentinel(kit):
    """Energy-shield emitter frame: heavy shoulder-mounted emitters, painted medium plates, a back frame with arcs,
    hip emitters and a hexagonal shield projector on the left forearm."""
    ctx, L = kit.ctx, kit.L
    with kit.cls("quilt"):
        suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.0015))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    with kit.cls("paint"):
        torso_panels(kit, rg, off=0.016, gap=0.009, rows_abs=2, back=True, female=True)
    A.seam_strips(kit, "Glow")
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        with kit.cls("paint"):
            limb_panels(kit, rg, s_, arm_off=0.013, leg_off=0.015, cover=0.55)
            pauldron(kit, s_, 0.8, layers=2, offset=0.02)
        with kit.cls("paint2"):
            joint_cap(kit, bt, bs, (0, -1, 0.05), 0.034, 0.018)
        shoulder_emitter(kit, s_)
        with kit.cls("gunmetal"):
            hp_ = L[bt] + np.array((s_ * 0.11, -0.01, 0.03))
            emitter(kit, "Hips", hp_, np.array((s_ * 1.0, -0.3, 0)), (0, 0, 1), 0.018)
    p, n = kit.torso(sp2 + 0.0, math.pi)
    with kit.cls("gunmetal"):
        kit.box("Spine2", p + n * 0.042, n, (0, 0, 1), (0.09, 0.12, 0.032), 0.006)
    for k in range(3):
        kit.box("Spine2", p + n * 0.0585 + np.array((0, 0, 0.03 - 0.03 * k)), n, (0, 0, 1), (0.066, 0.006, 0.002), 0.0008, mat="Glow")
    p, n = kit.limb("LeftForeArm", 0.5, math.radians(-30), push=0.03)
    axf = nrm(L["LeftHand"] - L["LeftForeArm"])
    with kit.cls("paint2"):
        kit.plate("LeftForeArm", p, n, axf, 0.044, 0.054, offset=0.0, thickness=0.006, crown=0.004, chamfer=0.003, groove=0.0, segs=24,
                  poly=hex_outline(), corner=0.12, clearance=0.003, cast_r=0.1)
    with kit.cls("gunmetal"):
        emitter(kit, "LeftForeArm", p + n * 0.012, n, axf, 0.012)
    with kit.cls("paint2"):
        collar(kit, rows=1, height=0.024, push=0.012, segs=10)
    return suit


SETS = {
    "kael": {"vanguard_mk2": ("Vanguard Mk II", set_vanguard_mk2), "aegis_exo": ("Aegis Exo-Frame", set_aegis_exo),
             "phantom_stealth": ("Phantom Stealth", set_phantom_stealth), "samurai_neo": ("Samurai Neo", set_samurai_neo)},
    "lyra": {"netrunner_x": ("Netrunner X", set_netrunner_x), "valkyrie": ("Valkyrie", set_valkyrie),
             "phantom_stealth_f": ("Phantom Stealth", set_phantom_stealth), "arc_sentinel": ("Arc Sentinel", set_arc_sentinel)},
}

# designed colours (sRGB) per set; decal = marking colour; quilt = suit quilting style
LOOK = {
    "vanguard_mk2": dict(paint="#5b636c", paint2="#c8641e", nylon="#4b4f3d", suit="#26282c", polymer="#2f3236", gunmetal="#3c4148",
                         decal="#e9e3cf", hazard="#e0a01e", quilt="none", glow="#00e5ff", glow2="#ff8a1f", screen="#38d8ff"),
    "aegis_exo": dict(paint="#4a5058", paint2="#c9d63a", nylon="#3d4236", suit="#33372f", polymer="#1e2023", gunmetal="#30343a",
                      decal="#d6ff3a", hazard="#d6ff3a", quilt="diamond", glow="#00e5ff", glow2="#9dff3a", screen="#38d8ff"),
    "phantom_stealth": dict(hex=True, paint="#1c1e21", paint2="#2a6dff", nylon="#141518", suit="#121316", polymer="#1a1c1f", gunmetal="#25282d",
                            decal="#4c5866", hazard="#4c5866", quilt="channel", glow="#00e5ff", glow2="#ff2bd6", screen="#2a6dff"),
    "samurai_neo": dict(paint="#7a0d14", paint2="#121214", lacquer="#8c0d16", lacquer2="#0d0d0f", nylon="#1b1b22", suit="#151619",
                        polymer="#1a1a1d", gunmetal="#2a2a2e", cord="#23233a", decal="#d9b45a", hazard="#d9b45a", quilt="none",
                        glow="#ff2bd6", glow2="#ffd040", screen="#ff5ad6"),
    "netrunner_x": dict(paint="#e6e8ec", paint2="#ff3fd2", polymer="#e3e5ea", nylon="#1d1e24", suit="#17181d", gunmetal="#2b2d33",
                        cord="#2a1f3a", decal="#8a5bff", hazard="#ff3fd2", quilt="rib", glow="#ff2bd6", glow2="#8a5bff", screen="#ff5ae0"),
    "valkyrie": dict(paint="#cdd1da", paint2="#7c5cd6", nylon="#2b2438", suit="#2a2238", polymer="#d8dbe2", gunmetal="#3a3546",
                     decal="#c9a24c", hazard="#7c5cd6", quilt="diamond", glow="#8ad8ff", glow2="#ff2bd6", screen="#b79bff"),
    "phantom_stealth_f": dict(hex=True, paint="#1c1e21", paint2="#7a3dff", nylon="#141518", suit="#121316", polymer="#1a1c1f", gunmetal="#25282d",
                              decal="#544c66", hazard="#544c66", quilt="channel", glow="#ff2bd6", glow2="#8a5bff", screen="#7a3dff"),
    "arc_sentinel": dict(paint="#4a5466", paint2="#dfe3ea", nylon="#252833", suit="#1d2028", polymer="#30353f", gunmetal="#2b313b",
                         decal="#62dcff", hazard="#e8c02a", quilt="diamond", glow="#62dcff", glow2="#ff2bd6", screen="#62dcff"),
}


# ============================================================================= high-poly + bakes


def class_attr(obj, kit):
    """Per-vertex material class from the plate id (hard pieces) or the slot (suit / gaskets)."""
    me = obj.data
    pl = gear.attr(obj, "plate")
    slot_v = np.zeros(len(me.vertices), np.int32)
    idx = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", idx)
    for p, mi in zip(me.polygons, idx):
        for v in p.vertices:
            slot_v[v] = mi
    cls = np.zeros(len(me.vertices))
    for i, (pid, sl) in enumerate(zip(pl, slot_v)):
        name = kit.cls_of.get(int(round(pid)))
        if name is None:
            name = "suit" if sl == 1 else "paint"
        if sl == 1 and name in HARD:
            name = "rubber"
        if sl == 0 and name not in HARD:
            name = "steel"
        cls[i] = CI[name]
    gear.set_attr(obj, "cls", cls)
    return cls


def rivets_part(obj, kit, spacing=0.026):
    """HP floaters: rivet rows inset ~1 cm from the edges of every armour panel."""
    me = obj.data
    pl = gear.attr(obj, "plate"); wr = gear.attr(obj, "wear")
    co = gear.get_co(obj)
    part = Part("rivets")
    pts = []
    rng = np.random.default_rng(3)
    idx = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", idx)
    ctx = kit.ctx
    for p in me.polygons:
        if idx[p.index] != 0:
            continue
        vs = list(p.vertices)
        pid = int(round(pl[vs[0]]))
        if pid not in kit.panel_ids:
            continue
        w = wr[vs].mean()
        if not (0.2 < w < 0.8):
            continue
        n = np.array(p.normal)
        c = co[vs].mean(0)
        hit, bn, _, _ = ctx.tree.find_nearest(Vector(c), 0.3)
        if hit is None or np.dot(n, np.array(bn)) < 0.3:
            continue
        pts.append((c, n))
    rng.shuffle(pts)
    keep = []
    grid = {}
    for c, n in pts:
        key = tuple((c // spacing).astype(int))
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if np.linalg.norm(c - q) < spacing:
                            ok = False
        if ok:
            grid.setdefault(key, []).append(c)
            keep.append((c, n))
    for c, n in keep:
        r, u, nn = gear.frame_from(n, (0, 0, 1) if abs(n[2]) < 0.9 else (1, 0, 0))
        verts, faces = [], []
        for k in range(8):
            t = 2 * math.pi * k / 8
            d = r * math.cos(t) + u * math.sin(t)
            verts.append(c + d * 0.0026 - nn * 0.0005)
            verts.append(c + d * 0.0021 + nn * 0.0011)
        verts.append(c + nn * 0.0016)
        top = len(verts) - 1
        for k in range(8):
            k2 = (k + 1) % 8
            faces.append([k * 2, k2 * 2, k2 * 2 + 1, k * 2 + 1])
            faces.append([k * 2 + 1, k2 * 2 + 1, top])
        part.add(np.array(verts), faces, "Armor")
    return part.build(mat_order=SLOTS, max_edge=None) if part.F else None, len(keep)


def make_hp(lp, kit):
    hp = lp.copy()
    hp.data = lp.data.copy()
    bpy.context.scene.collection.objects.link(hp)
    hp.name = lp.name + "_HP"
    hp.modifiers.clear()
    hp.parent = None
    hp.matrix_world = Matrix.Identity(4)
    if hp.data.shape_keys:
        hp.shape_key_clear()
    me = hp.data
    bm = bmesh.new(); bm.from_mesh(me)
    edges = [e for e in bm.edges if len(e.link_faces) == 2 and all(f.material_index == 0 for f in e.link_faces)
             and e.calc_face_angle(0.0) > math.radians(28)]
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=0.0011, segments=2, profile=0.5, affect="EDGES", clamp_overlap=True)
    bm.to_mesh(me); bm.free()
    m = hp.modifiers.new("sub", "SUBSURF"); m.levels = m.render_levels = 2
    gear.apply_modifiers(hp)
    rv, nr = rivets_part(lp, kit)
    if rv is not None:
        hp = gear.join([hp, rv], lp.name + "_HP")
    C.log("HP tris", C.tris(hp), "rivets", nr)
    return hp


def bake(lp, hp, size, ao_size=1024):
    """Cycles selected-to-active bakes: tangent-space normal (size) and AO (ao_size) for the Armor and SuitSecondary
    slots. Returns {slot: {"normal": (H,W,3), "ao": (H,W)}}."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("bake_world")
    imgs = {}
    dummy = bpy.data.images.new("bk_dummy", 8, 8, alpha=False)
    added = []

    def setup(kind, res):
        for i, m in enumerate(lp.data.materials):
            m.use_nodes = True
            nt = m.node_tree
            n = nt.nodes.new("ShaderNodeTexImage")
            if m.name in ("Armor", "SuitSecondary"):
                img = bpy.data.images.new(f"bk_{kind}_{m.name}", res, res, alpha=False, float_buffer=True)
                img.colorspace_settings.name = "Non-Color"
                imgs[(kind, m.name)] = img
                n.image = img
            else:
                n.image = dummy
            nt.nodes.active = n
            added.append((nt, n))

    def cleanup():
        for nt, n in added:
            nt.nodes.remove(n)
        added.clear()
    hidden = []
    for o in bpy.data.objects:
        if o not in (lp, hp) and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    hp.select_set(True); lp.select_set(True)
    bpy.context.view_layer.objects.active = lp
    t0 = time.time()
    setup("normal", size)
    sc.cycles.samples = 1
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", use_selected_to_active=True, cage_extrusion=0.003, max_ray_distance=0.007,
                        margin=8, margin_type="EXTEND", use_clear=True)
    cleanup()
    C.log("normal bake", round(time.time() - t0, 1))
    t0 = time.time()
    setup("ao", ao_size)
    sc.cycles.samples = 24
    sc.world.light_settings.distance = 0.08
    for attr in ("visible_diffuse", "visible_glossy", "visible_shadow", "visible_transmission", "visible_volume_scatter", "visible_camera"):
        setattr(lp, attr, False)
    bpy.ops.object.bake(type="AO", use_selected_to_active=True, cage_extrusion=0.003, max_ray_distance=0.007, margin=8, margin_type="EXTEND",
                        use_clear=True)
    for attr in ("visible_diffuse", "visible_glossy", "visible_shadow", "visible_transmission", "visible_volume_scatter", "visible_camera"):
        setattr(lp, attr, True)
    cleanup()
    C.log("ao bake", round(time.time() - t0, 1))
    out = {}
    for slot in ("Armor", "SuitSecondary"):
        d = {}
        for kind, res in (("normal", size), ("ao", ao_size)):
            img = imgs.get((kind, slot))
            a = np.empty(res * res * 4, np.float32); img.pixels.foreach_get(a); a = a.reshape(res, res, 4)
            if kind == "ao":
                a = a[..., 0]
                if res != size:
                    a = np.kron(a, np.ones((size // res, size // res), np.float32))
                    a = TB.blur(a, 1)
            else:
                a = a[..., :3]
            d[kind] = a
            bpy.data.images.remove(img)
        out[slot] = d
    bpy.data.images.remove(dummy)
    for o in hidden:
        o.hide_render = False
    sc.render.engine = "BLENDER_EEVEE"
    return out


# ============================================================================= texture synthesis

MAT = {  # class: (albedo key or hex, metallic, smoothness, pattern)
    "suit": ("suit", 0.0, 0.3, "knit"), "quilt": ("suit", 0.0, 0.28, "quilt"), "nylon": ("nylon", 0.0, 0.2, "nylon"),
    "rubber": ("#141516", 0.0, 0.3, "grain"), "paint": ("paint", 0.0, 0.42, "paint"), "paint2": ("paint2", 0.0, 0.45, "paint"),
    "lacquer": ("lacquer", 0.0, 0.84, "lacquer"), "lacquer2": ("lacquer2", 0.0, 0.8, "lacquer"), "steel": ("#a2a8ae", 1.0, 0.56, "brushed"),
    "chrome": ("#dfe3e8", 1.0, 0.88, "none"), "gunmetal": ("gunmetal", 1.0, 0.5, "brushed"), "carbon": ("#111214", 0.0, 0.74, "carbon"),
    "polymer": ("polymer", 0.0, 0.36, "stipple"), "gold": ("#c9a24c", 1.0, 0.66, "brushed"), "cord": ("cord", 0.0, 0.3, "cord"),
}
CHIP_TO = {"paint": "steel", "paint2": "steel", "lacquer": "lacquer2", "lacquer2": "lacquer", "polymer": "polymer"}


def hexcol(look, key):
    v = look.get(key, key)
    if not str(v).startswith("#"):
        v = "#808080"
    return C.hx(v)


def plate_decals(pid, lx, ly, rng_seed, look, area):
    """Invented decals for one plate in its local 2-D coords: returns (mask (N,), colour (N,3), smooth_add)."""
    import tattoo
    n = len(lx)
    mask = np.zeros(n, np.float32)
    col = np.zeros((n, 3), np.float32)
    rng = np.random.default_rng(int(pid * 7919 + rng_seed) % (2 ** 31))
    if area < 0.0075 or rng.random() > 0.45:
        return mask, col
    kind = rng.choice(["glyphs", "serial", "chevron", "unit"], p=[0.35, 0.25, 0.2, 0.2])
    cx = np.percentile(lx, rng.uniform(25, 75)); cy = np.percentile(ly, rng.uniform(30, 70))
    pat = tattoo.Pat()
    s = 0.012
    if kind == "glyphs":
        for k in range(int(rng.integers(3, 6))):
            pat.glyph(rng, cx + k * s * 1.25, cy, s, 0, frame=False)
        pat.line([(cx - s * 0.7, cy - s * 0.85), (cx + s * 1.25 * 4.5, cy - s * 0.85)], 0.0007, 0)
    elif kind == "serial":
        for k in range(int(rng.integers(10, 18))):
            w = rng.choice([0.0006, 0.0012, 0.0018])
            pat.line([(cx + k * 0.0026, cy - 0.005), (cx + k * 0.0026, cy + 0.005)], w, 0)
        for k in range(3):
            pat.glyph(rng, cx + 0.05 + k * 0.009, cy, 0.008, 0, frame=False)
    elif kind == "chevron":
        for k in range(5):
            x0 = cx + k * 0.009
            pat.poly([(x0, cy - 0.012), (x0 + 0.0045, cy - 0.012), (x0 + 0.0135, cy + 0.012), (x0 + 0.009, cy + 0.012)], 0)
        pat.line([(cx - 0.004, cy - 0.015), (cx + 0.05, cy - 0.015), (cx + 0.05, cy + 0.015), (cx - 0.004, cy + 0.015), (cx - 0.004, cy - 0.015)],
                 0.0009, 0)
    else:
        pat.dot(cx, cy, 0.016, 0.0022, 0)
        pat.poly([(cx, cy + 0.011), (cx + 0.0095, cy - 0.0055), (cx - 0.0095, cy - 0.0055)], 0)
        pat.dot(cx, cy, 0.0035, 0, 0)
    cov = pat.eval(lx, ly, soft=0.00022)
    m = np.clip(cov[0], 0, 1)
    if kind == "chevron":
        c = hexcol(look, "hazard")
        inner = m
        mask = inner
        col[:] = c
    else:
        mask = m
        col[:] = hexcol(look, "decal")
    return mask.astype(np.float32), col


def synth(obj, slot, size, maps, look, kit, seed=1.0):
    """Per-texel PBR synthesis for one slot (see module doc)."""
    T = TB.raster([obj], slot, size, attrs=("plate", "wear", "cavity", "lx", "ly", "bx", "by", "bz", "cls"))
    cov = T.cov.reshape(size, size)
    idx = np.where(T.cov)[0]
    P = T.P[idx].astype(np.float64)
    Nrm = T.N[idx].astype(np.float64)
    Aa = {k: v[idx] for k, v in T.A.items()}
    cls = np.clip(np.round(Aa["cls"]).astype(int), 0, len(CLASSES) - 1)
    pid = np.round(Aa["plate"]).astype(int)
    lx, ly = Aa["lx"], Aa["ly"]
    bp = np.stack([Aa["bx"], Aa["by"], Aa["bz"]], 1)
    nob = np.abs(bp).sum(1) < 1e-6
    bp[nob] = P[nob]
    mpt = float(np.median(T.mpt[T.cov]))
    def per(p_):
        return max(p_, 4.5 * mpt)
    ys, xs = np.divmod(idx, size)
    U = xs * mpt; V = ys * mpt
    n = len(idx)
    # baked maps
    nb = maps["normal"].reshape(-1, 3)[idx] * 2 - 1
    ao = np.clip(maps["ao"].reshape(-1)[idx], 0, 1)
    nimg = maps["normal"] * 2 - 1
    gx = np.gradient(nimg[..., 0], axis=1); gy = np.gradient(nimg[..., 1], axis=0)
    curv_img = -(gx + gy)
    curv_img = np.where(cov, curv_img, 0)
    curv = TB.blur(curv_img, 1).reshape(-1)[idx] * 6.0
    convex = np.clip(curv, 0, 1); concave = np.clip(-curv, 0, 1)
    wear_attr = Aa["wear"]
    # per-class base
    alb = np.zeros((n, 3)); met = np.zeros(n); smo = np.zeros(n); h = np.zeros(n)
    noise = TB.fbm3(P, 120.0, 3, seed)
    noise2 = TB.fbm3(P, 900.0, 2, seed + 3)
    for name, (ak, m_, s_, pat) in MAT.items():
        sel = cls == CI[name]
        if not sel.any():
            continue
        alb[sel] = hexcol(look, ak) if not ak.startswith("#") else C.hx(ak)
        met[sel] = m_; smo[sel] = s_
        u, v, p3 = U[sel], V[sel], P[sel]
        if pat == "knit":
            k1 = np.sin(u / per(0.0012) * math.pi) * np.sin(v / per(0.001) * math.pi)
            h[sel] += 0.00004 * k1
            alb[sel] *= (0.95 + 0.05 * k1)[:, None]
            b3 = bp[sel]
            sd = np.full(sel.sum(), 1.0)
            Lm = kit.L
            tz = (b3[:, 2] > Lm["Hips"][2] - 0.05) & (b3[:, 2] < Lm["Neck"][2]) & (np.abs(b3[:, 0]) < 0.2)
            sd = np.where(tz, np.minimum(np.abs(np.abs(b3[:, 0]) - 0.105), np.abs(b3[:, 2] - (Lm["Hips"][2] + 0.09))), sd)
            sd = np.minimum(sd, np.abs(b3[:, 2] - (Lm["Spine2"][2] + 0.07)) + (~tz) * 1.0)
            seam = 1 - ss(0.0007, 0.0016, sd)
            stitch = (np.abs(sd - 0.0035) < 0.0006) * (np.sin((b3[:, 0] + b3[:, 1] + b3[:, 2]) / 0.004 * math.pi) > 0.3)
            pad = np.zeros(sel.sum())
            for jb in ("LeftLeg", "RightLeg", "LeftForeArm", "RightForeArm"):
                pad = np.maximum(pad, 1 - ss(0.05, 0.075, np.linalg.norm(b3 - Lm[jb], axis=1)))
            q1 = (b3[:, 0] + b3[:, 2]) / 0.03; q2 = (b3[:, 0] - b3[:, 2]) / 0.03
            dq = np.minimum(np.abs(q1 - np.round(q1)), np.abs(q2 - np.round(q2)))
            h[sel] += -0.0007 * seam + 0.0009 * pad * (ss(0.0, 0.5, dq) ** 0.6) + 0.0002 * pad
            alb[sel] *= (1 - 0.35 * seam - 0.15 * pad * (1 - ss(0.0, 0.3, dq)))[:, None] * (1 + 0.3 * stitch)[:, None]
        elif pat == "nylon":
            w1 = np.sin(u / per(0.0013) * math.pi); w2 = np.sin(v / per(0.0013) * math.pi)
            wv = np.sign(w1 * w2) * np.abs(w1 * w2) ** 0.5
            h[sel] += 0.00006 * wv
            alb[sel] *= (0.9 + 0.08 * wv + 0.06 * noise[sel])[:, None]
        elif pat == "quilt":
            q = look.get("quilt", "diamond")
            b3 = bp[sel]
            if q == "diamond":
                q1 = (b3[:, 0] + b3[:, 2]) / 0.05; q2 = (b3[:, 0] - b3[:, 2]) / 0.05
                d = np.minimum(np.abs(q1 - np.round(q1)), np.abs(q2 - np.round(q2)))
            elif q == "rib":
                q1 = b3[:, 2] / 0.022
                d = np.abs(q1 - np.round(q1))
            else:  # channel
                q1 = (b3[:, 2] + 0.35 * np.abs(b3[:, 0])) / 0.035
                d = np.abs(q1 - np.round(q1))
            puff = ss(0.0, 0.5, d)
            h[sel] += 0.0012 * (puff ** 0.6) - 0.0004
            st = (d < 0.06) & (np.sin((q1 if q != "diamond" else q1 + q2) * 60.0) > 0.2)
            alb[sel] *= (0.82 + 0.18 * puff)[:, None] * (1 + 0.25 * st)[:, None]
            k1 = np.sin(u / per(0.0012) * math.pi) * np.sin(v / per(0.001) * math.pi)
            h[sel] += 0.00004 * k1
        elif pat == "grain":
            h[sel] += 0.00003 * TB.vnoise3(p3, 2500.0, 2.0)
        elif pat == "paint":
            h[sel] += 0.000008 * noise2[sel]
            alb[sel] *= (0.96 + 0.06 * noise[sel])[:, None]
            smo[sel] += 0.06 * (noise[sel] - 0.5)
        elif pat == "lacquer":
            alb[sel] *= (0.93 + 0.1 * TB.fbm3(p3, 40.0, 3, 7.0))[:, None]
            h[sel] += 0.000004 * noise2[sel]
        elif pat == "brushed":
            st = TB.vnoise3(np.stack([u * 8.0, v * 0.12, u * 0.0], 1), min(900.0, 0.25 / mpt), 4.0)
            h[sel] += 0.000012 * st
            alb[sel] *= (0.92 + 0.12 * st)[:, None]
            smo[sel] += 0.12 * (st - 0.5)
        elif pat == "carbon":
            cw = per(0.0045)
            i = np.floor(u / cw); j = np.floor(v / cw)
            hor = ((i + np.floor(j / 1.0)) % 4) < 2
            fib = np.where(hor, np.sin(v / per(0.0011) * math.pi), np.sin(u / per(0.0011) * math.pi))
            tow = np.where(hor, np.sin((v / cw - j) * math.pi), np.sin((u / cw - i) * math.pi))
            h[sel] += 0.00005 * tow
            alb[sel] = (0.035 + 0.05 * np.where(hor, 1.0, 0.45) * (0.7 + 0.3 * fib))[:, None] * np.ones(3)
            smo[sel] = 0.78
        elif pat == "stipple":
            h[sel] += 0.000012 * TB.vnoise3(p3, 1800.0, 6.0)
            alb[sel] *= (0.96 + 0.05 * noise[sel])[:, None]
            if look.get("hex"):
                hx_ = np.stack([u / 0.007 - v / 0.007 * 0.5, v / 0.007 * 0.866], 1)
                cell = np.round(hx_)
                dd = np.abs(hx_ - cell).max(1)
                edge_ = ss(0.36, 0.46, dd)
                tint = TB.hash3(np.stack([cell[:, 0], cell[:, 1], cell[:, 0] * 0], -1), 2.0)
                h[sel] += -0.00025 * edge_ + 0.00006 * tint
                alb[sel] *= (0.85 + 0.3 * tint - 0.35 * edge_)[:, None]
                smo[sel] += 0.25 * tint - 0.1
        elif pat == "cord":
            ph = (u + v) / per(0.0022) * math.pi
            br = np.sin(ph) * np.sin((u - v) / per(0.0022) * math.pi)
            h[sel] += 0.00009 * br
            alb[sel] *= (0.8 + 0.25 * br)[:, None]
    # panel lines, vents and decals on hard painted plates
    hard_paint = np.isin(cls, [CI[c] for c in ("paint", "paint2", "lacquer", "lacquer2", "polymer", "gunmetal")])
    if hard_paint.any():
        ids = np.unique(pid[hard_paint])
        for k in ids:
            if k <= 0:
                continue
            sel = np.where(hard_paint & (pid == k))[0]
            if len(sel) < 400:
                continue
            area = len(sel) * mpt * mpt
            rng = np.random.default_rng(int(k) * 31 + 7)
            x_, y_ = lx[sel], ly[sel]
            # 1-2 panel lines
            for j in range(int(rng.integers(1, 3))):
                ang = rng.choice([0.0, math.pi / 2, math.pi / 4, -math.pi / 4]) + rng.normal(0, 0.05)
                c0 = np.percentile(x_ * math.cos(ang) + y_ * math.sin(ang), rng.uniform(30, 70))
                d = np.abs(x_ * math.cos(ang) + y_ * math.sin(ang) - c0)
                g = 1 - ss(0.00045, 0.0009, d)
                h[sel] -= 0.0006 * g
                alb[sel] *= (1 - 0.45 * g)[:, None]
            if area > 0.004 and rng.random() < 0.35:   # vent slots
                vx = np.percentile(x_, rng.uniform(25, 60)); vy = np.percentile(y_, rng.uniform(25, 60))
                ang = rng.uniform(0, math.pi)
                xr = (x_ - vx) * math.cos(ang) + (y_ - vy) * math.sin(ang)
                yr = -(x_ - vx) * math.sin(ang) + (y_ - vy) * math.cos(ang)
                vent = np.zeros(len(sel))
                for s5 in range(5):
                    dd = np.maximum(np.abs(xr - s5 * 0.006) - 0.0016, np.abs(yr) - 0.011)
                    vent = np.maximum(vent, 1 - ss(-0.0003, 0.0003, dd))
                h[sel] -= 0.0014 * vent
                alb[sel] *= (1 - 0.7 * vent)[:, None]
                smo[sel] -= 0.2 * vent
            m, c = plate_decals(k, x_, y_, seed, look, area)
            if m.any():
                alb[sel] = alb[sel] * (1 - m[:, None]) + c * m[:, None]
                smo[sel] += 0.05 * m
                h[sel] += 0.00002 * m
    # wear: chips on edges (painted / lacquered / polymer) revealing the layer below, scratches, grime
    edge = np.clip(convex * 1.1 + ss(0.9, 1.0, wear_attr) * 0.5, 0, 1.5)
    chipn = TB.fbm3(P, 300.0, 3, seed + 11)
    chips = ss(0.86, 0.95, edge * 0.85 + chipn * 0.35) * (edge > 0.45)
    for src, dst in CHIP_TO.items():
        sel = (cls == CI[src]) & (chips > 0.01)
        if not sel.any():
            continue
        ak, m_, s_, _ = MAT[dst]
        dcol = hexcol(look, ak) if not ak.startswith("#") else C.hx(ak)
        w = chips[sel][:, None]
        if src == "polymer":
            dcol = alb[sel] * 1.18
        alb[sel] = alb[sel] * (1 - w) + dcol * w
        met[sel] = met[sel] * (1 - w[:, 0]) + m_ * w[:, 0]
        smo[sel] = smo[sel] * (1 - w[:, 0]) + s_ * w[:, 0]
        h[sel] -= 0.00006 * w[:, 0]
    scr = np.zeros(n)
    for k in range(3):
        ang = 0.7 + k * 1.1
        uu = U * math.cos(ang) + V * math.sin(ang)
        line = np.abs(((uu + TB.hash3(np.floor(P * 20.0), 3.0 + k) * 0.05) % 0.031) - 0.0155)
        scr = np.maximum(scr, (line < 0.00018) * (TB.vnoise3(P, 70.0, 4.0 + k) > 0.66))
    hardsel = np.isin(cls, [CI[c] for c in HARD])
    alb[hardsel] = alb[hardsel] * (1 - 0.25 * scr[hardsel, None]) + 0.55 * 0.25 * scr[hardsel, None]
    smo[hardsel] += 0.1 * scr[hardsel]
    grime = np.clip(concave * 1.3 + (1 - ao) * 0.9, 0, 1) * (0.55 + 0.45 * TB.fbm3(P, 30.0, 2, seed + 5))
    alb *= (1 - 0.42 * grime)[:, None]
    smo -= 0.18 * grime
    smo = np.clip(smo, 0.05, 0.95)
    # normals: baked HP normal + detail height (reoriented normal mapping)
    H = np.zeros((size, size), np.float32)
    H.reshape(-1)[idx] = h
    H = TB.dilate(H[..., None], cov, 4)[..., 0]
    dn = TB.height_to_normal(H, T.mpt.reshape(size, size), 1.0).reshape(-1, 3)[idx] * 2 - 1
    t = nb + np.array((0, 0, 1.0))
    u_ = dn * np.array((-1, -1, 1.0))
    r = t * (t * u_).sum(1, keepdims=True) / np.maximum(t[:, 2:3], 1e-4) - u_
    r = nrm_rows(r)
    # assemble images
    base = np.zeros((size * size, 3), np.float32); base[idx] = np.clip(alb, 0, 1)
    nimg = np.zeros((size * size, 3), np.float32); nimg[:] = (0.5, 0.5, 1.0); nimg[idx] = r * 0.5 + 0.5
    mask = np.zeros((size * size, 4), np.float32)
    mask[idx, 0] = np.clip(met, 0, 1); mask[idx, 1] = np.clip(ao * 0.85 + 0.15, 0, 1); mask[idx, 2] = 1.0; mask[idx, 3] = smo
    out = []
    for img, ch in ((base, 3), (nimg, 3), (mask, 4)):
        im = img.reshape(size, size, ch)
        im = TB.dilate(im, cov, 10)
        out.append(im)
    return out


# ============================================================================= previews / export


def preview_mats(obj, look, files_a, files_s):
    mats = {}
    if files_a:
        mats["Armor"] = texstage.preview_mat("pv3_Armor_" + obj.name, os.path.join(TEX_DIR, files_a[0]), os.path.join(TEX_DIR, files_a[1]),
                                             maskmap=os.path.join(TEX_DIR, files_a[2]))
    if files_s:
        mats["SuitSecondary"] = texstage.preview_mat("pv3_Suit_" + obj.name, os.path.join(TEX_DIR, files_s[0]), os.path.join(TEX_DIR, files_s[1]),
                                                     maskmap=os.path.join(TEX_DIR, files_s[2]))
    mats["Glow"] = studio.flat("pv3_Glow_" + obj.name, look["glow"], 0.3, 0, (look["glow"], 8.0))
    mats["Glow2"] = studio.flat("pv3_Glow2_" + obj.name, look["glow2"], 0.3, 0, (look["glow2"], 8.0))
    mats["Screen"] = studio.flat("pv3_Screen_" + obj.name, "#06141a", 0.15, 0, (look["screen"], 2.0))
    for i, m in enumerate(obj.data.materials):
        if m and m.name in mats:
            obj.data.materials[i] = mats[m.name]


def drop_strays3(obj, body, kit, limit=0.17):
    """Delete connected pieces that reach further than `limit` from the body unless they are intended free pieces."""
    tree = BVHTree.FromPolygons([v.co.copy() for v in body.data.vertices], [list(p.vertices) for p in body.data.polygons])
    pl = gear.attr(obj, "plate")
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    far = [v.index for v in bm.verts if int(round(pl[v.index])) not in kit.free_ids and (tree.find_nearest(v.co, 1.0)[3] or 0) > limit]
    if not far:
        bm.free(); return 0
    seen, kill = set(), []
    for vi in far:
        if vi in seen:
            continue
        stack = [bm.verts[vi]]
        while stack:
            v = stack.pop()
            if v.index in seen:
                continue
            seen.add(v.index); kill.append(v)
            stack += [e.other_vert(v) for e in v.link_edges if e.other_vert(v).index not in seen]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(obj.data); bm.free(); obj.data.update()
    C.log("dropped stray pieces, verts", len(kill))
    return len(kill)


def main():
    a = C.args()
    cid = a[0]
    table = SETS[cid]
    sel = a[1].split(",") if len(a) > 1 and not a[1].startswith("--") else list(table)
    size = int(a[a.index("--size") + 1]) if "--size" in a else 2048
    for d in (TEX_DIR, PREV_DIR, THUMB_DIR, os.path.join(C.CACHE, "catalog", "armour")):
        os.makedirs(d, exist_ok=True)
    for sid in sel:
        t0 = time.time()
        rig, body = C.load_ref(cid)
        ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
        kit = Kit3(ctx, cid)
        label, fn = table[sid]
        look = LOOK[sid]
        suit = fn(kit)
        objs = finalize(kit, suit)
        obj = gear.join(objs, f"{cid}_{sid}")
        unify_slots(obj)
        drop_strays3(obj, body, kit)
        fill_weights(obj)
        class_attr(obj, kit)
        ntri = C.tris(obj)
        C.log(sid, "tris", ntri, "verts", len(obj.data.vertices), "shapes", len(obj.data.shape_keys.key_blocks) - 1, "build s", round(time.time() - t0, 1))
        TB.pack([obj], "Armor", margin=0.003)
        TB.pack([obj], "SuitSecondary", margin=0.003)
        hp = make_hp(obj, kit)
        maps = bake(obj, hp, size)
        bpy.data.objects.remove(hp, do_unlink=True)
        base = f"{cid}_{sid}"
        files = {}
        for slot, label_ in (("Armor", "Armor"), ("SuitSecondary", "Suit")):
            imgs = synth(obj, slot, size, maps[slot], look, kit)
            fs = [f"{base}_{label_}_BaseColor.png", f"{base}_{label_}_Normal.png", f"{base}_{label_}_MaskMap.png"]
            C.write_png(imgs[0], os.path.join(TEX_DIR, fs[0]), "RGB")
            C.write_png(imgs[1], os.path.join(TEX_DIR, fs[1]), "RGB")
            C.write_png(imgs[2], os.path.join(TEX_DIR, fs[2]), "RGBA")
            files[slot] = fs
        C.log(sid, "textures", round(time.time() - t0, 1))
        # previews
        obj["custom"] = 1
        studio.hero_materials(cid, hide_outfit=True, keep=KEEPS[cid])
        obj.hide_render = False; obj.hide_viewport = False
        import hair_preview
        hair = hair_preview.load_default_hair(cid)
        preview_mats(obj, look, files["Armor"], files["SuitSecondary"])
        H_ = float(max(C.get_co(body)[:, 2]))
        aim = Vector((0, 0, H_ * 0.53))
        studio.world_and_lights(aim, 2.2, rim=1.0, yaw=30, env=12.0)
        studio.camera(studio.view(aim, 30, 4, 4.6 * H_ / 1.85), aim, 50)
        studio.render(os.path.join(THUMB_DIR, f"armour_{cid}_{sid}.png"), 512, 256)
        for tag, yaw, pitch, dist, aimz in (("front", 0, 3, 4.4, 0.53), ("q34", 35, 4, 4.4, 0.53), ("back", 180, 4, 4.4, 0.53),
                                            ("chest", 25, 3, 1.4, 0.76), ("detail", 55, 8, 0.75, 0.72)):
            ai = Vector((0, 0, H_ * aimz))
            studio.world_and_lights(ai, 2.2 if dist > 2 else 1.0, rim=1.0, yaw=yaw, env=12.0)
            studio.camera(studio.view(ai, yaw, pitch, dist * H_ / 1.85), ai, 50)
            studio.render(os.path.join(PREV_DIR, f"{cid}_{sid}_{tag}.png"), 640)
        for i in range(len(obj.data.materials)):
            obj.data.materials[i] = gear.get_mat(SLOTS[i])
        if hair:
            bpy.data.objects.remove(hair, do_unlink=True)
        if "--no-export" not in a:
            for m in obj.modifiers:
                if m.type == "ARMATURE":
                    m.object = rig
            C.export_fbx(os.path.join(OUT_DIR, f"{cid}_{sid}.fbx"), [obj], armature=rig)
            e = {"id": sid, "label": label, "hero": cid, "file": f"Armour/{cid}_{sid}", "kind": "skinned", "replaces": REPLACES[cid],
                 "keeps": KEEPS[cid], "thumb": f"Thumbs/armour_{cid}_{sid}", "tris": ntri,
                 "blendShapes": [k.name for k in obj.data.shape_keys.key_blocks[1:]] if obj.data.shape_keys else [],
                 "materials": {
                     "Armor": {"baseMap": f"Armour/Textures/{base}_Armor_BaseColor", "normal": f"Armour/Textures/{base}_Armor_Normal",
                               "maskMap": f"Armour/Textures/{base}_Armor_MaskMap", "tint": "#ffffff"},
                     "SuitSecondary": {"baseMap": f"Armour/Textures/{base}_Suit_BaseColor", "normal": f"Armour/Textures/{base}_Suit_Normal",
                                       "maskMap": f"Armour/Textures/{base}_Suit_MaskMap", "tint": "#ffffff"},
                     "Glow": {"color": look["glow"], "intensity": 4.0}, "Glow2": {"color": look["glow2"], "intensity": 4.0},
                     "Screen": {"color": look["screen"], "intensity": 1.5}},
                 "maskMapLayout": "R metallic, G occlusion, B detail mask, A smoothness",
                 "pipeline": "v3: high-poly bake (normal, AO, curvature) + PBR material classes; designed colours, tint white"}
            with open(os.path.join(C.CACHE, "catalog", "armour", f"{cid}_{sid}.json"), "w") as f:
                json.dump(e, f, indent=1)
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.CACHE, f"armour_{cid}_{sid}.blend"), compress=True)
        C.log(sid, "done", round(time.time() - t0, 1))
    import catalog
    catalog.merge()


if __name__ == "__main__":
    main()
