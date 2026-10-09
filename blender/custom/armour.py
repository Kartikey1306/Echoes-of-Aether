"""Ultra-high-tech armour sets for the heroes (skinned to the mixamo_unity rig, body customisation blend shapes
transferred with a surface binding, 2K BaseColor/Normal/MaskMap atlases for the Armor and SuitSecondary slots).

  blender -b --python blender/custom/armour.py -- <cid> [set,...] [--no-export] [--no-tex]

Every set is a complete outfit layer: a fitted under-suit (SuitSecondary, follows the body exactly: same skin weights,
so the body never pokes through) + hard plates (Armor, mostly rigid per bone) + emissive strips (Glow, Glow2) and
display panels (Screen). It replaces the base outfit pieces listed in REPLACES (Unity hides them); boots, gloves and
facial cyberware stay. Material slots: Armor, SuitSecondary, Glow, Glow2, Screen.
"""
import bpy, os, sys, math, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
import common as C
import gear, texbake as TB, texstage
from gear import Part, plate, shell, light_strip, tube, rbox, bolt, strap, surface_path, limb_coords
import studio
from common import ss, nrm, nrm_rows

OUT_DIR = os.path.join(C.CUSTOM_OUT, "Armour")
TEX_DIR = os.path.join(OUT_DIR, "Textures")
THUMB_DIR = os.path.join(C.CUSTOM_OUT, "Thumbs")
PREV_DIR = os.path.join(C.PREVIEWS, "armour")
SLOTS = ["Armor", "SuitSecondary", "Glow", "Glow2", "Screen"]

REPLACES = {
    "kael": ["Top", "Pants", "Collar", "ChestRig", "ChestPlate", "PauldronL", "PauldronLameL", "PauldronR", "PauldronLameR",
             "KneePadL", "KneePadR", "ForearmGuardR", "Interface", "Belt", "Conduit"],
    "lyra": ["Top", "Jacket", "Pants", "Harness", "ChestUnit", "ChestCore", "ShoulderR", "ForearmGuardL", "HipModule", "ThighRig",
             "ConduitL", "ConduitR"],
}
KEEPS = {"kael": ["Body", "Boots", "Gloves", "Cyberware", "Eyes", "Brows", "Lashes", "Teeth", "Tongue"],
         "lyra": ["Body", "Boots", "Gloves", "Cyberware", "Visor", "Eyes", "Brows", "Lashes", "Teeth", "Tongue"]}


# ============================================================================= kit


class Kit:
    def __init__(self, ctx, cid):
        self.ctx, self.cid = ctx, cid
        self.L, self.T = ctx.L, ctx.T
        self.parts = {}          # skin key -> Part   (key: bone name | "suit" | tuple of bones)
        self.shells = []         # (object, rigid bone or None, weight_bones or None)
        self.pid = 1.0

    def P(self, key):
        if key not in self.parts:
            self.parts[key] = Part(f"arm_{key if isinstance(key, str) else '_'.join(key)}")
        return self.parts[key]

    def next_id(self):
        self.pid += 1
        return self.pid

    # ------------------------------------------------------------------ placements
    def torso(self, z, phi, push=0.0, R=0.4):
        """Point on the torso surface at height z, angle phi. Rays that land on an A-posed arm (beyond the torso's
        half-width at that height) are re-cast from just outside the torso."""
        p, n = self.ctx.torso_point(z, phi, push=push, R=R)
        hw = self.torso_hw(z)
        if abs(p[0]) > hw + 0.02:
            r2 = max(hw * 1.15, 0.12)
            p, n = self.ctx.torso_point(z, phi, push=push, R=r2)
        return p, n

    def torso_hw(self, z):
        if not hasattr(self, "_hw"):
            co = self.ctx.basis
            m = (self.ctx.region["torso"] + self.ctx.region["hips"] + self.ctx.region["neck"]) > 0.6
            self._tz, self._tx = co[m, 2], np.abs(co[m, 0])
            self._hw = {}
        k = round(z, 3)
        if k not in self._hw:
            sel = np.abs(self._tz - z) < 0.02
            self._hw[k] = float(self._tx[sel].max()) if sel.any() else 0.18
        return self._hw[k]

    def limb(self, bone, t, phi, push=0.0, R=0.14):
        return self.ctx.limb_point(bone, t, phi, push=push, ref=(0, 0, 1), R=R)

    def axis(self, bone, t):
        return self.L[bone] + (self.T[bone] - self.L[bone]) * t

    def plate(self, key, center, out, up, a, b, **kw):
        kw.setdefault("mat_top", "Armor"); kw.setdefault("mat_edge", "Armor"); kw.setdefault("mat_wall", "Armor")
        kw.setdefault("plate_id", self.next_id())
        return plate(self.ctx, self.P(key), center, out, up, a, b, **kw)

    def strip(self, key, pts, push=0.0012, width=0.003, height=0.0013, mat="Glow", n=None):
        P_, N_ = surface_path(self.ctx, pts, n or max(10, len(pts) * 5), push=push)
        light_strip(self.P(key), P_, N_, width, height, mat=mat)
        return P_, N_

    def box(self, key, center, n, up, size, bevel=0.003, mat="Armor"):
        r, u, nn = gear.frame_from(n, up)
        rbox(self.P(key), center, r, u, nn, size, bevel, 2, mat=mat, attrs={"plate": self.next_id(), "wear": 0.0})
        return r, u, nn


def ring_points(kit, bone, t, phis, push=0.004):
    pts, nn = [], []
    for ph in phis:
        p, n = kit.limb(bone, t, ph, push=push)
        pts.append(p); nn.append(n)
    return np.array(pts), np.array(nn)


# ============================================================================= under-suit


def suit_mask(ctx, cid, neck_top=0.6, sleeve="wrist", legs="ankle"):
    """Body vertices covered by the under-suit: torso, arms (to the wrist), legs (to the ankle), lower neck. Always a
    superset of the body faces the exported hero lost under its outfit (except hands and feet, which keep gloves and
    boots)."""
    R = ctx.region
    co = ctx.basis
    L = ctx.L
    m = (R["torso"] + R["hips"] + R["uarmL"] + R["uarmR"] + R["farmL"] + R["farmR"] + R["thighL"] + R["thighR"] + R["shinL"] + R["shinR"]) > 0.35
    m |= R["neck"] > 0.3
    nk0, nk1 = L["Neck"][2], L["Head"][2]
    m &= co[:, 2] < nk0 + (nk1 - nk0) * neck_top
    m &= (R["head"] < 0.2) & (R["handL"] < 0.45) & (R["handR"] < 0.45) & (R["footL"] < 0.5) & (R["footR"] < 0.5)
    exposed = gear.attr(ctx.body, "exposed") > 0.5
    need = ~exposed & (R["head"] < 0.2) & (R["handL"] < 0.3) & (R["handR"] < 0.3) & (R["footL"] < 0.3) & (R["footR"] < 0.3)
    need &= co[:, 2] > L["LeftFoot"][2] + 0.03
    missing = need & ~m
    m |= need
    return m, int(missing.sum())


def build_suit(kit, name, offset, neck_top=0.6, rim=0.004, smooth=2):
    ctx = kit.ctx
    m, added = suit_mask(ctx, kit.cid, neck_top)
    C.log("suit mask verts", int(m.sum()), "added for coverage", added)
    obj = shell(ctx, name, m, offset, mats=("SuitSecondary",), smooth=smooth, subdiv=0, rim=rim, min_clear=0.0035, cover=False,
                stack=True, bsmooth=10)
    return obj


def stock_offset(ctx, base=0.0045, torso=0.002, limbs=0.0):
    L = ctx.L

    def off(P, N):
        # never thinner than 5.5 mm; +3 mm on the arms (elbow flexion) and around the knees
        o = np.full(len(P), max(base, 0.0045))
        o += torso * ((P[:, 2] > L["Hips"][2] - 0.05) & (P[:, 2] < L["Neck"][2]) & (np.abs(P[:, 0]) < 0.19))
        # thinner at the inner elbow (a thick shell folds into the crease under flexion)
        for eb in ("LeftForeArm", "RightForeArm"):
            o -= 0.0015 * (np.linalg.norm(P - L[eb], axis=1) < 0.06)
        for kb in ("LeftLeg", "RightLeg"):
            o += 0.002 * (np.linalg.norm(P - L[kb], axis=1) < 0.08)
        return o
    return off


# ============================================================================= pieces (shared)


def pauldron(kit, side, size=1.0, layers=3, offset=0.016, crest=False, fin=0, key=None, poly=None):
    L = kit.L
    s_ = side
    bone = "LeftArm" if s_ > 0 else "RightArm"
    sh = L[bone]
    piv = sh + np.array((-s_ * 0.035, 0.0, -0.045))
    c = sh + np.array((s_ * 0.04, 0.0, 0.07))
    k = key or bone
    kit.plate(k, c, nrm(np.array((s_ * 0.78, 0, 0.66))), (-s_ * 0.66, 0, 0.78), 0.12 * size, 0.11 * size, mode="radial", pivot=piv,
              poly=poly or [(-1, 0.55), (-0.45, 1), (0.6, 1), (1, 0.35), (1, -0.75), (0.5, -1), (-0.5, -1), (-1, -0.6)], corner=0.3,
              offset=offset, thickness=0.008, crown=0.012, chamfer=0.004, groove=0.66, groove_depth=0.0018, ridge=0.004,
              bolts=[(-0.62, 0.62), (0.62, 0.62), (0.0, -0.78)], gasket="SuitSecondary", cast_r=0.3, segs=36)
    for j in range(layers - 1):
        t = 0.2 + 0.16 * j
        p_, n_ = kit.limb(bone, t, math.radians(-12 * s_), R=0.14)
        axp = kit.axis(bone, t)
        up_ = nrm(L[bone] - kit.T[bone])
        kit.plate(k, p_, n_, up_, (0.088 - 0.006 * j) * size, 0.034 * size, mode="radial", pivot=axp,
                  poly=[(-1, 1), (1, 1), (1, -0.7), (0.8, -1), (-0.8, -1), (-1, -0.7)], corner=0.2,
                  offset=offset + 0.004 + 0.005 * (layers - 1 - j), thickness=0.006, crown=0.003, chamfer=0.003,
                  bolts=[(-0.82, 0.4), (0.82, 0.4)], segs=28, cast_r=0.14)
    return sh


def limb_guard(kit, bone, t0, t1, phi, width, offset=0.006, n_exp=5.0, key=None, groove=0.62, segs=28, poly=None, mat_top="Armor",
               crown=0.003, thickness=0.006, bolts=None):
    L = kit.L
    tm = (t0 + t1) * 0.5
    a_, b_ = L[bone], kit.T[bone]
    ln = np.linalg.norm(b_ - a_)
    c = a_ + (b_ - a_) * tm
    p, n = kit.limb(bone, tm, phi)
    return kit.plate(key or bone, p, n, nrm(b_ - a_), width, (t1 - t0) * ln * 0.5, n_exp=n_exp, mode="radial", pivot=c, offset=offset,
                     thickness=thickness, crown=crown, chamfer=0.003, groove=groove, segs=segs, cast_r=0.12, poly=poly, mat_top=mat_top,
                     bolts=bolts if bolts is not None else [(-0.8, 0.0), (0.8, 0.0)])


def joint_cap(kit, bone_upper, bone_lower, side_dir, radius=0.034, offset=0.008, key=None, n_exp=2.0, groove=0.6):
    """Elbow / knee cap: a round plate on the outside of the joint, rigid to the lower bone."""
    j = kit.L[bone_lower]
    up = nrm(kit.L[bone_upper] - j)
    d = nrm(np.asarray(side_dir, float))
    hit, n = kit.ctx.cast(j + d * 0.2, -d, 0.25)
    if hit is None:
        hit, n = j + d * 0.05, d
    return kit.plate(key or bone_lower, hit, nrm(n + d), up, radius, radius, n_exp=n_exp, mode="radial", pivot=j, offset=offset,
                     thickness=0.007, crown=0.006, chamfer=0.003, groove=groove, segs=28, cast_r=0.12, bolts=[(0, 0)])


def collar(kit, rows=2, height=0.022, push=0.01, segs=10, key=("Neck", "Spine2")):
    """Gorget: rows of curved plates around the neck base."""
    L = kit.L
    nk = L["Neck"]
    for r in range(rows):
        z = nk[2] - 0.035 + r * (height * 0.9)
        for k in range(segs):
            ph = -math.pi + (k + 0.5) * 2 * math.pi / segs
            d = np.array((math.sin(ph), -math.cos(ph), 0.0))
            c0 = np.array((0.0, nk[1] + 0.005, z))
            hit, n = kit.ctx.cast(c0 + d * 0.25, -d, 0.3)
            if hit is None:
                continue
            kit.plate(key, hit, nrm(n * 0.7 + d * 0.3 + np.array((0, 0, 0.35 - 0.15 * r))), (0, 0, 1), 0.024, height * 0.5, n_exp=6,
                      mode="radial", pivot=c0, offset=push + 0.006 * (rows - 1 - r), thickness=0.005, crown=0.002, chamfer=0.0025,
                      segs=20, cast_r=0.25, groove=0.0)


def reactor(kit, key, center, n, up, r=0.034):
    """Chest reactor: round housing, glowing core, ring of screen segments."""
    nn = nrm(n)
    rr, u, _ = gear.frame_from(nn, up)
    part = kit.P(key)
    ring = np.array([center + (rr * math.cos(t) + u * math.sin(t)) * r for t in np.linspace(0, 2 * math.pi, 33)])
    tube(part, ring + nn * 0.004, 0.006, 10, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0})
    ring2 = np.array([center + (rr * math.cos(t) + u * math.sin(t)) * r * 0.62 for t in np.linspace(0, 2 * math.pi, 33)])
    tube(part, ring2 + nn * 0.006, 0.0026, 8, mat="Glow2")
    # core disc (fan) and spokes
    verts = [center + nn * 0.0085] + [center + nn * 0.006 + (rr * math.cos(t) + u * math.sin(t)) * r * 0.5 for t in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
    faces = [[0, 1 + i, 1 + (i + 1) % 24] for i in range(24)]
    part.add(np.array(verts), faces, "Glow")
    for k in range(6):
        t = k * math.pi / 3
        d = rr * math.cos(t) + u * math.sin(t)
        rbox(part, center + d * r * 0.82 + nn * 0.007, nrm(np.cross(nn, d)), d, nn, (0.006, 0.012, 0.004), 0.0012, 1, mat="Screen")
    # housing back plate
    verts = [center + nn * 0.001] + [center + nn * 0.001 + (rr * math.cos(t) + u * math.sin(t)) * r * 1.12 for t in np.linspace(0, 2 * math.pi, 32, endpoint=False)]
    part.add(np.array(verts), [[0, 1 + i, 1 + (i + 1) % 32] for i in range(32)], "Armor", None, {"plate": kit.next_id()})


def slab(kit, key, pts, origin, r, u, n, thickness, mat="Armor"):
    """Free-standing bevelled prism (fins, blades): 2-D outline pts in the (r, u) plane at origin, extruded along n."""
    pts = np.asarray(pts, float)
    m = len(pts)
    top = [origin + r * x + u * y + n * thickness * 0.5 for x, y in pts]
    bot = [origin + r * x + u * y - n * thickness * 0.5 for x, y in pts]
    # inset top/bottom for a chamfer
    c = pts.mean(0)
    ins = [(c + (p - c) * 0.88) for p in pts]
    topi = [origin + r * x + u * y + n * thickness * 0.75 for x, y in ins]
    boti = [origin + r * x + u * y - n * thickness * 0.75 for x, y in ins]
    V = np.array(top + bot + topi + boti)
    F = [[2 * m + i for i in range(m)], [3 * m + i for i in range(m)][::-1]]
    for i in range(m):
        j = (i + 1) % m
        F.append([i, j, m + j, m + i][::-1])
        F.append([i, 2 * m + i, 2 * m + j, j][::-1])
        F.append([m + i, m + j, 3 * m + j, 3 * m + i][::-1])
    w = [1.0] * (2 * m) + [0.0] * (2 * m)
    kit.P(key).add(V, F, mat, None, {"plate": [kit.next_id()] * len(V), "wear": w})


def hex_outline():
    return [(math.cos(a), math.sin(a)) for a in np.radians([90, 30, -30, -90, -150, 150])]


# ============================================================================= armour panel shells


class Region:
    """Body-space selectors for armour panels (vectorised over body vertices)."""

    def __init__(self, ctx):
        self.ctx = ctx
        co = ctx.basis
        self.co = co
        self.x, self.y, self.z = co[:, 0], co[:, 1], co[:, 2]
        self.R = ctx.region
        L = ctx.L
        self.L = L
        self.cy = L["Spine1"][1]

    def limb(self, bone, side_ref=(0, 0, 1.0)):
        """(t 0..1 along the bone, phi around (0 = up/front reference), radial) for all body vertices."""
        a, b = self.L[bone], self.ctx.T[bone]
        t, phi, r = limb_coords(self.co, a, b, side_ref)
        return t / max(np.linalg.norm(b - a), 1e-6), phi, r


def panel(kit, name, mask, offset, rim=0.006, mat="Armor", weight_bones=None, bone=None, smooth=6, bsmooth=14, flat=0.0):
    """Hard armour panel: a shell over the body faces in `mask`, `offset` metres out (scalar or fn(P, N)), with a
    solid rim (thickness). Skinned with weights interpolated from the body (or rigid to `bone`)."""
    ctx = kit.ctx
    if mask.sum() < 6:
        return None
    from mathutils.kdtree import KDTree
    out_idx = np.where(~mask)[0]
    kd = KDTree(len(out_idx))
    for i in out_idx:
        kd.insert(Vector(ctx.basis[i]), int(i))
    kd.balance()
    pid = kit.next_id()

    def attrs_fn(bp, vn):
        d = np.array([kd.find(Vector(p))[2] for p in bp])
        return {"wear": 1 - ss(0.004, 0.018, d), "plate": np.full(len(bp), pid), "lx": bp[:, 0] - bp[:, 0].mean(), "ly": bp[:, 2] - bp[:, 2].mean(),
                "cavity": np.zeros(len(bp))}
    off = offset if callable(offset) else (lambda P, N, o=offset: np.full(len(P), o))
    try:
        o = shell(ctx, f"{name}", mask, off, mats=(mat,), smooth=smooth, subdiv=0, rim=rim, min_clear=0.004, cover=False, stack=False,
                  bsmooth=bsmooth, attrs_fn=attrs_fn)
    except Exception as ex:
        print("PANEL FAIL", name, ex)
        return None
    if len(o.data.polygons) == 0:
        bpy.data.objects.remove(o, do_unlink=True)
        return None
    kit.shells.append((o, bone, weight_bones))
    return o


def band(z0, z1, zr):
    return (zr >= z0) & (zr <= z1)


def torso_panels(kit, rg, style="heavy", off=0.02, gap=0.007, rows_abs=3, back=True, chest_top=None, female=False):
    L = kit.L
    x, y, z = rg.x, rg.y, rg.z
    R = rg.R
    tor = (R["torso"] + R["hips"] * 0.5) > 0.5
    sp1, sp2, nk, hips = L["Spine1"][2], L["Spine2"][2], L["Neck"][2], L["Hips"][2]
    front = y < rg.cy - 0.005
    ct = chest_top if chest_top is not None else nk - 0.045
    cb = sp1 + (0.0 if not female else 0.02)
    lim = 0.17 if not female else 0.15
    outs = []
    for s_ in (1, -1):
        m = tor & front & (z > cb) & (z < ct) & (x * s_ > gap) & (np.abs(x) < lim)
        outs.append(panel(kit, f"chest{s_}", m, off))
    if rows_abs:
        zs = np.linspace(hips + 0.02, cb - gap, rows_abs + 1)
        for r in range(rows_abs):
            for s_ in (1, -1):
                m = tor & front & (z > zs[r] + gap * 0.5) & (z < zs[r + 1] - gap * 0.5) & (x * s_ > gap * 0.6) & (np.abs(x) < 0.12)
                outs.append(panel(kit, f"abs{r}{s_}", m, off * 0.7 + 0.002 * r))
    if back:
        for s_ in (1, -1):
            m = tor & ~front & (z > sp1 - 0.04) & (z < nk - 0.05) & (x * s_ > gap * 1.6) & (np.abs(x) < 0.16)
            outs.append(panel(kit, f"back{s_}", m, off * 0.9))
        m = tor & ~front & (z > hips + 0.02) & (z < sp1 - 0.04 - gap) & (np.abs(x) < 0.12)
        outs.append(panel(kit, "lumbar", m, off * 0.7))
    return outs


def limb_panels(kit, rg, side, arm_off=0.016, leg_off=0.018, upper=True, fore=True, thigh=True, shin=True, cover=0.62, gap_t=0.03):
    S = "Left" if side > 0 else "Right"
    R = rg.R
    outs = []
    def sel(bone, reg, t0, t1, phi_c, half):
        t, phi, r = rg.limb(bone)
        dphi = np.abs((phi - phi_c + math.pi) % (2 * math.pi) - math.pi)
        return (R[reg] > 0.5) & (t > t0) & (t < t1) & (dphi < half)
    if upper:
        m = sel(S + "Arm", "uarmL" if side > 0 else "uarmR", 0.3, 0.86, math.radians(-90 * side), math.pi * cover)
        outs.append(panel(kit, f"uarm{side}", m, arm_off))
    if fore:
        m = sel(S + "ForeArm", "farmL" if side > 0 else "farmR", 0.1, 0.9, math.radians(-30 * side), math.pi * cover)
        outs.append(panel(kit, f"farm{side}", m, arm_off))
    if thigh:
        m = sel(S + "UpLeg", "thighL" if side > 0 else "thighR", 0.16, 0.78, math.radians(0), math.pi * cover * 0.8)
        outs.append(panel(kit, f"thigh{side}", m, leg_off))
    if shin:
        m = sel(S + "Leg", "shinL" if side > 0 else "shinR", 0.12, 0.72, math.radians(0), math.pi * cover * 0.75)
        outs.append(panel(kit, f"shin{side}", m, leg_off))
    return outs


# ============================================================================= sets


def set_vanguard_mk2(kit):
    """Heavy powered plate: layered pauldrons, chest reactor, segmented abdomen, gorget, back power pack, full limb
    plating, tassets and greaves."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.002))
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    # chest: two pectoral plates + sternum plate carrying the reactor
    for s_ in (1, -1):
        p, n = kit.torso(sp2 + 0.03, s_ * 0.42, R=0.4)
        kit.plate("Spine2", p, nrm(n + np.array((0, 0, 0.15))), (0, 0, 1), 0.095, 0.075, offset=0.008, thickness=0.009, crown=0.012,
                  chamfer=0.004, groove=0.7, groove_depth=0.0018, ridge=0.003, gasket="SuitSecondary", segs=40,
                  poly=[(-1, 0.6), (-0.7, 1), (0.9, 1), (1, 0.4), (0.85, -0.6), (0.4, -1), (-0.8, -1), (-1, -0.4)] if s_ > 0 else
                  [(1, 0.6), (0.7, 1), (-0.9, 1), (-1, 0.4), (-0.85, -0.6), (-0.4, -1), (0.8, -1), (1, -0.4)], corner=0.18,
                  bolts=[(-0.7 * s_, 0.75), (0.75 * s_, -0.7)])
    p, n = kit.torso(sp2 + 0.02, 0.0, R=0.4)
    kit.plate("Spine2", p, n, (0, 0, 1), 0.05, 0.07, offset=0.02, thickness=0.008, crown=0.006, chamfer=0.004,
              poly=[(-1, 1), (1, 1), (0.8, -0.6), (0, -1), (-0.8, -0.6)], corner=0.2, segs=32)
    reactor(kit, "Spine2", p + n * 0.034, n, (0, 0, 1), 0.03)
    # abdomen: 3 rows x 2 segmented plates
    for r in range(3):
        z = sp1 - 0.035 - r * 0.055
        key = "Spine1" if r == 0 else "Spine"
        for s_ in (1, -1):
            p, n = kit.torso(z, s_ * 0.2, R=0.4)
            kit.plate(key, p, n, (0, 0, 1), 0.055, 0.027, offset=0.006 + 0.002 * (2 - r), thickness=0.006, crown=0.004, chamfer=0.003,
                      n_exp=5.0, segs=28, groove=0.0, bolts=[(-0.8 * s_, 0.0)])
    # side ribs
    for s_ in (1, -1):
        for r in range(2):
            p, n = kit.torso(sp1 - 0.02 - r * 0.06, s_ * 1.35, R=0.4)
            kit.plate("Spine1", p, n, (0, 0, 1), 0.035, 0.025, offset=0.005, thickness=0.005, crown=0.003, n_exp=4.0, segs=24, groove=0.0)
    # back plate + power pack
    for s_ in (1, -1):
        p, n = kit.torso(sp2 + 0.02, math.pi - s_ * 0.38, R=0.4)
        kit.plate("Spine2", p, n, (0, 0, 1), 0.09, 0.09, offset=0.008, thickness=0.008, crown=0.008, chamfer=0.004, groove=0.68,
                  segs=36, n_exp=4.0, bolts=[(-0.7, 0.7), (0.7, -0.7)])
    p, n = kit.torso(sp2 - 0.01, math.pi, R=0.4)
    r_, u_, n_ = kit.box("Spine2", p + n * 0.045, n, (0, 0, 1), (0.13, 0.17, 0.05), 0.008)
    for k in range(4):
        kit.box("Spine2", p + n * 0.071 + u_ * (0.05 - k * 0.028), n, (0, 0, 1), (0.09, 0.006, 0.003), 0.001, mat="Glow")
    for s_ in (1, -1):
        c = p + n * 0.045 + r_ * s_ * 0.075
        tube(kit.P("Spine2"), np.array([c + u_ * 0.08, c - u_ * 0.08]), 0.016, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0}, caps=True)
        tube(kit.P("Spine2"), np.array([c + u_ * 0.05 + n_ * 0.013, c - u_ * 0.05 + n_ * 0.013]), 0.004, 8, mat="Glow2")
    collar(kit, rows=2, height=0.024, push=0.012, segs=10)
    # shoulders
    for s_ in (1, -1):
        pauldron(kit, s_, 1.05, layers=3, offset=0.02)
        bone_u = "LeftArm" if s_ > 0 else "RightArm"
        bone_f = "LeftForeArm" if s_ > 0 else "RightForeArm"
        limb_guard(kit, bone_u, 0.5, 0.88, math.radians(-25 * s_), 0.04, offset=0.006)
        joint_cap(kit, bone_u, bone_f, (s_ * 0.5, 0.6, -0.2), 0.03)
        limb_guard(kit, bone_f, 0.1, 0.52, math.radians(-20), 0.034, offset=0.006, groove=0.6)
        limb_guard(kit, bone_f, 0.55, 0.92, math.radians(-20), 0.031, offset=0.006, groove=0.0)
        limb_guard(kit, bone_f, 0.2, 0.85, math.radians(-110), 0.022, offset=0.005, groove=0.0, n_exp=6.0)
        pts = [kit.limb(bone_f, t, math.radians(-62), push=0.0045)[0] for t in np.linspace(0.08, 0.92, 12)]
        kit.strip(bone_f, pts, push=0.0)
        # legs
        bt = "LeftUpLeg" if s_ > 0 else "RightUpLeg"
        bs = "LeftLeg" if s_ > 0 else "RightLeg"
        limb_guard(kit, bt, 0.2, 0.62, math.radians(10 * s_), 0.06, offset=0.008, n_exp=4.0, groove=0.66)
        limb_guard(kit, bt, 0.25, 0.75, math.radians(80 * s_), 0.04, offset=0.006, n_exp=5.0, groove=0.0)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.042, 0.012)
        limb_guard(kit, bs, 0.12, 0.62, math.radians(0), 0.05, offset=0.009, n_exp=4.0, groove=0.64)
        pts = [kit.limb(bs, t, math.radians(-10), push=0.0)[0] for t in np.linspace(0.14, 0.6, 8)]
        # tassets
        for k, ph in enumerate((0.35, 1.05)):
            p, n = kit.torso(hips - 0.065, s_ * ph, R=0.4)
            kit.plate(bt, p, n, (0, 0, 1), 0.06 if k == 0 else 0.045, 0.06, offset=0.012, thickness=0.006, crown=0.004, chamfer=0.003,
                      n_exp=4.0, segs=28, groove=0.62, poly=[(-1, 1), (1, 1), (0.85, -0.7), (0.4, -1), (-0.4, -1), (-0.85, -0.7)], corner=0.2)
        # glow seams on the chest plates and arms
        kit.strip("Spine2", [kit.torso(sp2 + 0.085, s_ * a, push=0.022)[0] for a in (0.12, 0.35, 0.6, 0.8)], push=0.0, mat="Glow")
    # belt
    rows = gear.ring_band(ctx, kit.P("Hips"), [np.array((0, L["Hips"][1], hips + 0.02)), np.array((0, L["Hips"][1], hips - 0.02))],
                          lambda ph: np.array((math.sin(ph), -math.cos(ph), 0.0)), None, [0.012, 0.012], n=40, mat="Armor",
                          attrs={"plate": kit.next_id(), "wear": 0.3})
    # forearm display (left)
    p, n = kit.limb("LeftForeArm", 0.6, math.radians(-20), push=0.016)
    r_, u_, n_ = kit.box("LeftForeArm", p, n, nrm(L["LeftHand"] - L["LeftForeArm"]), (0.034, 0.06, 0.01), 0.003)
    kit.box("LeftForeArm", p + n_ * 0.0052, n, nrm(L["LeftHand"] - L["LeftForeArm"]), (0.026, 0.046, 0.002), 0.0008, mat="Screen")
    return suit


def spine_key(kit, z):
    L = kit.L
    if z > L["Spine2"][2]:
        return "Spine2"
    if z > L["Spine1"][2]:
        return "Spine1"
    if z > L["Spine"][2]:
        return "Spine"
    return "Hips"


def side_bones(s_):
    S = "Left" if s_ > 0 else "Right"
    return S + "Arm", S + "ForeArm", S + "UpLeg", S + "Leg", S + "Hand"


def hub(kit, key, center, n, up, r=0.022, glow="Glow"):
    """Joint hub: short cylinder housing with a glowing ring."""
    nn = nrm(n)
    rr, u, _ = gear.frame_from(nn, up)
    part = kit.P(key)
    tube(part, np.array([center - nn * 0.004, center + nn * 0.012]), r, 16, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0}, caps=True)
    ring = np.array([center + nn * 0.0125 + (rr * math.cos(t) + u * math.sin(t)) * r * 0.7 for t in np.linspace(0, 2 * math.pi, 25)])
    tube(part, ring, 0.0018, 6, mat=glow)


def strut(kit, key, bone, t0, t1, phi, push=0.014, r=0.0065, piston=True):
    pts = [kit.limb(bone, t, phi, push=push)[0] for t in np.linspace(t0, t1, 9)]
    P_ = np.array(pts)
    tube(kit.P(key), P_, r, 10, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
    if piston:
        pts2 = [kit.limb(bone, t, phi + 0.35, push=push - 0.002)[0] for t in np.linspace(t0 + 0.08, t1 - 0.25, 6)]
        tube(kit.P(key), np.array(pts2), r * 0.45, 8, mat="Glow2", caps=True)
    return P_


def cuff(kit, key, bone, t, push=0.006, width=0.018, mat="Armor"):
    """Ring band around a limb; rays that miss the surface are replaced by the median radius (no stray spikes)."""
    L = kit.L
    a_, b_ = L[bone], kit.T[bone]
    ax = nrm(b_ - a_)
    c = a_ + (b_ - a_) * t
    r0 = nrm(np.cross(ax, (0, 0, 1.0)) if abs(ax[2]) < 0.9 else np.cross(ax, (1.0, 0, 0)))
    r1 = np.cross(ax, r0)
    tree = kit.ctx.outer_tree()
    pts, rad, nn = [], [], []
    for k in range(24):
        th = 2 * math.pi * k / 24
        d = r0 * math.cos(th) + r1 * math.sin(th)
        hit, n_, _, _ = tree.ray_cast(Vector(c + d * 0.12), Vector(-d), 0.13)
        if hit is not None and np.linalg.norm(np.array(hit) - c) < 0.058:
            rad.append(np.linalg.norm(np.array(hit) - c)); pts.append(d); nn.append(True)
        else:
            pts.append(d); rad.append(None); nn.append(False)
    if sum(nn) < 12:
        return
    med = float(np.median([r for r in rad if r is not None]))
    ring = [c + d * ((r if r is not None else med) + push) for d, r in zip(pts, rad)]
    ring.append(ring[0])
    P_ = np.array(ring); N_ = np.array([nrm(p - c) for p in ring])
    strap(kit.P(key), P_, N_, width, 0.005, mat=mat, attrs={"wear": 1.0, "plate": kit.next_id()}, caps=False)


def set_aegis_exo(kit):
    """Exoskeleton frame over techwear: vertebral spine column, shoulder yoke and actuators, limb struts with
    pistons, joint hubs, waist ring, wrist and ankle cuffs, light chest harness."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0065, 0.004))
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    # spine column
    zs = np.linspace(hips + 0.02, nk - 0.01, 9)
    prev = None
    for k, z in enumerate(zs):
        p, n = kit.torso(z, math.pi, push=0.004, R=0.4)
        key = spine_key(kit, z)
        r_, u_, n_ = kit.box(key, p + n * 0.01, n, (0, 0, 1), (0.042 - 0.002 * (k % 2), 0.024, 0.016), 0.004)
        kit.box(key, p + n * 0.0185, n, (0, 0, 1), (0.016, 0.012, 0.002), 0.0008, mat="Glow")
    spine = np.array([kit.torso(z, math.pi, push=0.028)[0] for z in np.linspace(hips + 0.02, nk - 0.01, 14)])
    tube(kit.P("suit"), spine, 0.0045, 8, mat="Glow2")
    # shoulder yoke + actuators
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        sh = L[bu]
        yoke = [kit.torso(sp2 + 0.04, math.pi - s_ * 0.25, push=0.016)[0], sh + np.array((-s_ * 0.06, 0.03, 0.075)),
                sh + np.array((-s_ * 0.05, -0.045, 0.06)), kit.torso(sp2 + 0.06, s_ * 0.45, push=0.014)[0]]
        P_ = gear.catmull(yoke, 18)
        tube(kit.P("Spine2"), np.array(P_), 0.008, 10, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
        d = nrm(np.array((s_ * 1.0, 0, 0.25)))
        hub(kit, bu, sh + d * 0.075 + np.array((0, 0, 0.0)), d, (0, 0, 1), 0.028)
        strut(kit, bu, bu, 0.18, 0.82, math.radians(-90 * s_ + 90 * s_) if False else math.radians(-100 * s_))
        hub(kit, bf, L[bf] + nrm(np.array((s_ * 0.6, 0.6, 0.0))) * 0.05, nrm(np.array((s_ * 0.6, 0.6, 0.0))), (0, 0, 1), 0.02)
        strut(kit, bf, bf, 0.1, 0.84, math.radians(-110 * s_ + 0 * s_))
        cuff(kit, bf, bf, 0.9, 0.006, 0.02)
        limb_guard(kit, bf, 0.2, 0.7, math.radians(-25), 0.028, offset=0.007, groove=0.0)
        # legs
        hp = L[bt] + np.array((s_ * 0.105, 0.0, 0.0))
        hub(kit, "Hips", hp, np.array((s_ * 1.0, 0, 0)), (0, 0, 1), 0.03)
        strut(kit, bt, bt, 0.12, 0.85, math.radians(90 * s_ * -1) if s_ < 0 else math.radians(-90), push=0.016, r=0.0075)
        kn = L[bs]
        hub(kit, bs, kn + np.array((s_ * 0.07, 0.0, 0.0)), np.array((s_ * 1.0, 0, 0)), (0, 0, 1), 0.024)
        strut(kit, bs, bs, 0.1, 0.72, math.radians(-90) if s_ > 0 else math.radians(90), push=0.016, r=0.0065)
        cuff(kit, bs, bs, 0.74, 0.008, 0.022)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.036, 0.01)
    # waist ring
    gear.ring_band(ctx, kit.P("Hips"), [np.array((0, L["Hips"][1], hips + 0.012)), np.array((0, L["Hips"][1], hips - 0.022))],
                   lambda ph: np.array((math.sin(ph), -math.cos(ph), 0.0)), None, [0.014, 0.014], n=40, mat="Armor",
                   attrs={"plate": kit.next_id(), "wear": 0.4})
    # chest harness
    for s_ in (1, -1):
        p, n = kit.torso(sp2 + 0.04, s_ * 0.38)
        kit.plate("Spine2", p, n, (0, 0, 1), 0.06, 0.05, offset=0.008, thickness=0.006, crown=0.006, chamfer=0.003, groove=0.65, segs=32,
                  poly=[(-1, 0.8), (-0.5, 1), (1, 1), (1, -0.4), (0.4, -1), (-1, -0.6)] if s_ > 0 else [(1, 0.8), (0.5, 1), (-1, 1), (-1, -0.4), (-0.4, -1), (1, -0.6)],
                  corner=0.2, bolts=[(0.6 * s_, 0.6)])
    p, n = kit.torso(sp2 - 0.01, 0.0)
    kit.plate("Spine2", p, n, (0, 0, 1), 0.04, 0.05, offset=0.014, thickness=0.006, crown=0.004, segs=28, n_exp=5)
    r_, u_, n_ = gear.frame_from(n, (0, 0, 1))
    kit.box("Spine2", p + n * 0.026, n, (0, 0, 1), (0.05, 0.06, 0.003), 0.001, mat="Screen")
    collar(kit, rows=1, height=0.026, push=0.012, segs=8)
    return suit


def stealth_panels(kit, female=False):
    ctx, L = kit.ctx, kit.L
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    hexo = hex_outline()
    ang = [(-1, 0.35), (-0.55, 1), (0.75, 1), (1, 0.2), (0.6, -1), (-0.8, -0.85)]
    kw = dict(mat_top="Screen", mat_edge="Armor", mat_wall="Armor", thickness=0.004, crown=0.003, chamfer=0.0022, groove=0.0)
    for s_ in (1, -1):
        p, n = kit.torso(sp2 + (0.02 if not female else 0.05), s_ * 0.42)
        kit.plate("Spine2", p, n, (0, 0, 1), 0.075 if not female else 0.06, 0.06, offset=0.004, segs=36,
                  poly=[(x * s_, y) for x, y in ang], corner=0.12, **kw)
        for r in range(3):
            p, n = kit.torso(sp1 - 0.02 - r * 0.05, s_ * 0.17)
            kit.plate("Spine1" if r == 0 else "Spine", p, n, (0, 0, 1), 0.026, 0.022, offset=0.004, segs=24, poly=hexo, corner=0.15, **kw)
        p, n = kit.torso(sp2 + 0.0, math.pi - s_ * 0.4)
        kit.plate("Spine2", p, n, (0, 0, 1), 0.07, 0.08, offset=0.004, segs=32, poly=[(x * s_, y) for x, y in ang], corner=0.12, **kw)
        bu, bf, bt, bs, bh = side_bones(s_)
        pauldron(kit, s_, 0.72 if not female else 0.62, layers=1, offset=0.008)
        limb_guard(kit, bu, 0.35, 0.8, math.radians(-95 * s_), 0.028, offset=0.004, poly=hexo, mat_top="Screen", groove=0.0)
        limb_guard(kit, bf, 0.12, 0.48, math.radians(-30), 0.026, offset=0.004, poly=ang, mat_top="Screen", groove=0.0)
        limb_guard(kit, bf, 0.52, 0.88, math.radians(-30), 0.024, offset=0.004, poly=ang, mat_top="Screen", groove=0.0)
        limb_guard(kit, bt, 0.2, 0.62, math.radians(15 * s_), 0.05, offset=0.004, poly=ang, mat_top="Screen", groove=0.0, n_exp=4)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.034, 0.008, groove=0.0)
        limb_guard(kit, bs, 0.15, 0.62, math.radians(0), 0.04, offset=0.005, poly=[(-1, 1), (1, 1), (0.7, -1), (-0.7, -1)], mat_top="Screen",
                   groove=0.0)
        # glow seams: torso side lines, outer arm, outer leg
        kit.strip("suit", [kit.torso(z, s_ * 1.45, push=0.0)[0] for z in np.linspace(hips - 0.02, sp2 + 0.12, 8)])
        kit.strip("suit", [kit.limb(bu, t, math.radians(-100 * s_), push=0.0)[0] for t in np.linspace(0.05, 0.95, 6)] +
                  [kit.limb(bf, t, math.radians(-100 * s_), push=0.0)[0] for t in np.linspace(0.05, 0.9, 6)])
        kit.strip("suit", [kit.limb(bt, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.08, 0.95, 7)] +
                  [kit.limb(bs, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.05, 0.75, 6)])
    kit.strip("suit", [kit.torso(z, 0.0, push=0.0)[0] for z in np.linspace(hips + 0.02, sp2 + 0.13, 9)], mat="Glow")
    kit.strip("suit", [kit.torso(z, math.pi, push=0.0)[0] for z in np.linspace(hips + 0.02, nk - 0.02, 10)], mat="Glow2")
    collar(kit, rows=2, height=0.02, push=0.008, segs=10)


def set_phantom_stealth(kit):
    """Sleek matte stealth suit: tight under-suit, angular light-bending panels (Screen slot = active camouflage),
    thin glow seams, stealth collar."""
    suit = build_suit(kit, "suit", stock_offset(kit.ctx, 0.0038, 0.001))
    stealth_panels(kit, female=kit.cid == "lyra")
    return suit


def lamella(kit, key, p, n, up, a=0.02, b=0.026, off=0.006, segs=12):
    """Small lamellar scale fitted to the surface right under it (short casts, so A-posed hands never get in)."""
    for cr in (0.1, 0.16):
        try:
            return kit.plate(key, p, n, up, a, b, offset=off, thickness=0.004, crown=0.002, chamfer=0.0018, groove=0.0, n_exp=6.0,
                             segs=segs, rings=[0.0, 0.6, None, 1.0], cast_r=cr)
        except ValueError:
            continue


def set_samurai_neo(kit):
    """Cyber-samurai: lamellar do (rows of scales with neon lacing), muna-ita chest plate with crest, large sode
    shoulder guards, kusazuri tassets, kote forearm plates, haidate and suneate."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.002))
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    rows = np.linspace(hips + 0.035, sp2 + 0.0, 5)
    for r, z in enumerate(rows):
        key = spine_key(kit, z)
        n_front = 11
        for k in range(n_front):
            ph = -1.75 + 3.5 * (k + 0.5 * (r % 2)) / n_front
            p, n = kit.torso(z, ph)
            lamella(kit, key, p, n, (0, 0, 1), 0.021, 0.025, off=0.006 + 0.0035 * r)
        for k in range(6):
            ph = math.pi - 1.1 + 2.2 * (k + 0.5 * (r % 2)) / 6
            p, n = kit.torso(z, ph)
            lamella(kit, key, p, n, (0, 0, 1), 0.024, 0.025, off=0.006 + 0.0035 * r)
        kit.strip(key, [kit.torso(z + 0.024, ph, push=0.012 + 0.0035 * r)[0] for ph in np.linspace(-1.8, 1.8, 12)], push=0.0, width=0.0024)
    # muna-ita + crest
    p, n = kit.torso(sp2 + 0.06, 0.0)
    kit.plate("Spine2", p, nrm(n + np.array((0, 0, 0.2))), (0, 0, 1), 0.13, 0.045, offset=0.026, thickness=0.007, crown=0.006, chamfer=0.003,
              groove=0.7, segs=40, poly=[(-1, 0.4), (-0.7, 1), (0.7, 1), (1, 0.4), (0.9, -1), (-0.9, -1)], corner=0.15,
              bolts=[(-0.85, 0.0), (0.85, 0.0)])
    reactor(kit, "Spine2", p + n * 0.04 + np.array((0, 0, 0.005)), n, (0, 0, 1), 0.022)
    p, n = kit.torso(sp2 + 0.03, math.pi)
    kit.plate("Spine2", p, n, (0, 0, 1), 0.12, 0.07, offset=0.02, thickness=0.006, crown=0.006, segs=36, groove=0.68)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        # sode: 4 wide lames hanging from the shoulder, outer side
        sh = L[bu]
        pauldron(kit, s_, 1.1, layers=4, offset=0.024)
        limb_panels(kit, rg, s_, arm_off=0.015, leg_off=0.017, upper=True, thigh=True, cover=0.5)
        cuff(kit, bf, bf, 0.93, 0.012, 0.016)
        for ph in (0.38, 1.15):
            for r in range(3):
                zz = hips - 0.035 - r * 0.048
                p, n = kit.torso(zz, s_ * ph)
                lamella(kit, bt, p, n, (0, 0, 1), 0.055, 0.025, off=0.024 + 0.005 * (2 - r), segs=16)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.04, 0.024)
    for r in range(3):
        for k in range(3):
            p, n = kit.torso(hips - 0.03 - r * 0.048, math.pi + (k - 1) * 0.55)
            lamella(kit, "Hips", p, n, (0, 0, 1), 0.055, 0.025, off=0.024 + 0.005 * (2 - r), segs=16)
    collar(kit, rows=1, height=0.032, push=0.02, segs=10)
    return suit


def set_netrunner_x(kit):
    """Lightweight plated bodysuit with a data-cable spine: sculpted bust and abdomen panels, slim forearm and shin
    shells, shoulder caps, nape port + lumbar hub joined by five cables, forearm display, side light lines."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0036, 0.0008))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    torso_panels(kit, rg, off=0.014, gap=0.008, rows_abs=2, back=False, female=True)
    for s_ in (1, -1):
        limb_panels(kit, rg, s_, arm_off=0.011, leg_off=0.013, upper=False, thigh=False, cover=0.5)
        bu, bf, bt, bs, bh = side_bones(s_)
        pauldron(kit, s_, 0.62, layers=2, offset=0.012)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.03, 0.014)
        kit.strip("suit", [kit.torso(z, s_ * 1.4, push=0.0)[0] for z in np.linspace(hips - 0.03, sp2 + 0.1, 8)], mat="Glow")
        kit.strip("suit", [kit.limb(bt, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.08, 0.95, 7)] +
                  [kit.limb(bs, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.05, 0.75, 6)], mat="Glow2")
    zs = np.linspace(nk + 0.02, hips + 0.03, 16)
    base = np.array([kit.torso(z, math.pi, push=0.0)[0] for z in zs])
    nrms = np.array([kit.torso(z, math.pi, push=0.0)[1] for z in zs])
    for k, dx in enumerate((-0.014, -0.007, 0.0, 0.007, 0.014)):
        P_ = base + nrms * (0.013 + 0.003 * (k % 2)) + np.array((dx, 0, 0)) * (1 + 0.5 * np.sin(np.linspace(0, math.pi, len(zs))))[:, None]
        tube(kit.P("suit"), np.array(gear.catmull(list(P_), 40)), 0.0036 if k != 2 else 0.0046, 8, mat="SuitSecondary" if k != 2 else "Glow")
    for z in np.linspace(nk - 0.04, hips + 0.06, 6):
        p, n = kit.torso(z, math.pi, push=0.004)
        key = spine_key(kit, z)
        kit.box(key, p + n * 0.014, n, (0, 0, 1), (0.046, 0.014, 0.014), 0.003)
        kit.box(key, p + n * 0.0215, n, (0, 0, 1), (0.034, 0.003, 0.002), 0.0006, mat="Glow2")
    p, n = kit.torso(nk - 0.01, math.pi, push=0.004)
    kit.box("Spine2", p + n * 0.016, n, (0, 0, 1), (0.056, 0.038, 0.02), 0.004)
    kit.box("Spine2", p + n * 0.0265, n, (0, 0, 1), (0.04, 0.022, 0.002), 0.0008, mat="Screen")
    p, n = kit.torso(hips + 0.03, math.pi, push=0.004)
    kit.box("Hips", p + n * 0.016, n, (0, 0, 1), (0.08, 0.045, 0.024), 0.005)
    p, n = kit.limb("LeftForeArm", 0.55, math.radians(-30), push=0.024)
    axf = nrm(L["LeftHand"] - L["LeftForeArm"])
    kit.box("LeftForeArm", p, n, axf, (0.032, 0.07, 0.008), 0.003)
    kit.box("LeftForeArm", p + n * 0.0045, n, axf, (0.026, 0.058, 0.002), 0.0008, mat="Screen")
    collar(kit, rows=1, height=0.024, push=0.01, segs=10)
    return suit


def set_valkyrie(kit):
    """Elegant segmented armour: sculpted bust plate, overlapping waist segments, shoulder fins, long tassets,
    pointed knee guards, flared vambraces and greaves (panel shells)."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.004, 0.001))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    tor = (rg.R["torso"] + rg.R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    panel(kit, "bust", tor & front & (z > sp1 + 0.02) & (z < nk - 0.05) & (np.abs(x) < 0.15), 0.016, rim=0.006)
    for r in range(3):
        z1 = sp1 + 0.01 - r * 0.042
        m = tor & (z > z1 - 0.036) & (z < z1) & (front | (np.abs(x) > 0.08)) & (np.abs(x) < 0.16)
        panel(kit, f"waist{r}", m, 0.012 + 0.004 * (2 - r), rim=0.005)
        kit.strip("suit", [kit.torso(z1 - 0.038, ph, push=0.0)[0] for ph in np.linspace(-1.2, 1.2, 9)], mat="Glow", width=0.003)
    panel(kit, "backplate", tor & ~front & (z > sp1 - 0.02) & (z < nk - 0.05) & (np.abs(x) < 0.14), 0.014, rim=0.006)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        sh = pauldron(kit, s_, 0.82, layers=2, offset=0.016,
                      poly=[(-1, 0.3), (-0.3, 1), (0.8, 0.9), (1, 0.2), (0.8, -0.8), (0.2, -1), (-0.6, -0.9), (-1, -0.4)])
        for j in range(3):
            base = sh + np.array((s_ * (0.04 + 0.022 * j), 0.025 + 0.012 * j, 0.11 - 0.014 * j))
            out = nrm(np.array((s_ * 0.9, 0.25, 0.2)))
            up = nrm(np.array((s_ * 0.15, 0.55, 1.0)))
            fwd = nrm(np.cross(out, up))
            slab(kit, bu, [(-0.02, 0.0), (0.02, 0.0), (0.012, 0.09 - 0.015 * j), (-0.004, 0.13 - 0.02 * j), (-0.014, 0.07 - 0.01 * j)],
                 base, fwd, up, out, 0.004)
            tip = base + up * (0.12 - 0.02 * j)
            tube(kit.P(bu), np.array([base + up * 0.01 + out * 0.005, tip + out * 0.005 - up * 0.012]), 0.0016, 6, mat="Glow")
        limb_panels(kit, rg, s_, arm_off=0.012, leg_off=0.014, cover=0.55)
        joint_cap(kit, bu, bf, (s_ * 0.5, 0.6, -0.2), 0.024, 0.016)
        for ph, ln in ((0.42, 0.1), (1.2, 0.085)):
            p, n = kit.torso(hips - 0.095, s_ * ph)
            kit.plate(bt, p, n, (0, 0, 1), 0.048, ln, offset=0.022, thickness=0.005, crown=0.004, chamfer=0.0025, groove=0.64, segs=28,
                      poly=[(-1, 1), (1, 1), (0.8, -0.6), (0, -1), (-0.8, -0.6)], corner=0.12)
        kn = L[bs]
        hit, nn = ctx.cast(kn + np.array((0, -0.2, 0.0)), (0, 1, 0), 0.3)
        kit.plate(bs, hit, nrm(nn), (0, 0, 1), 0.04, 0.065, mode="radial", pivot=kn, offset=0.022, thickness=0.006, crown=0.008, chamfer=0.003,
                  groove=0.0, segs=28, poly=[(-1, 0.4), (0, 1), (1, 0.4), (0.8, -0.8), (0, -1), (-0.8, -0.8)], corner=0.1, cast_r=0.14)
    p, n = kit.torso(sp2 + 0.065, 0.0)
    hub(kit, "Spine2", p + n * 0.024, n, (0, 0, 1), 0.013, glow="Glow2")
    collar(kit, rows=1, height=0.024, push=0.012, segs=10)
    return suit


def set_arc_sentinel(kit):
    """Energy-shield emitter frame: medium panels, a back frame with two arcs over the shoulders ending in emitter
    nodes, a hexagonal shield projector on the left forearm, hip emitters."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.0015))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    torso_panels(kit, rg, off=0.016, gap=0.009, rows_abs=2, back=True, female=True)
    seam_strips(kit, "Glow")
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        limb_panels(kit, rg, s_, arm_off=0.013, leg_off=0.015, cover=0.55)
        pauldron(kit, s_, 0.78, layers=2, offset=0.02)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.034, 0.018)
        b0 = kit.torso(sp2 + 0.02, math.pi - s_ * 0.45, push=0.04)[0]
        top = L[bu] + np.array((-s_ * 0.03, 0.07, 0.17))
        end = L[bu] + np.array((s_ * 0.025, -0.05, 0.13))
        arc = np.array(gear.catmull([b0, b0 + np.array((0, 0.05, 0.1)), top, end], 30))
        tube(kit.P("Spine2"), arc, 0.009, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
        tg = np.gradient(arc, axis=0)
        side = nrm_rows(np.cross(tg, np.array((1.0, 0, 0))))
        tube(kit.P("Spine2"), arc[3:-3] + side[3:-3] * 0.009, 0.0024, 6, mat="Glow")
        emitter(kit, "Spine2", end + np.array((0, -0.006, 0.0)), nrm(np.array((s_ * 0.3, -1, 0.5))), (0, 0, 1), 0.022)
        hp = L[bt] + np.array((s_ * 0.11, -0.01, 0.03))
        emitter(kit, "Hips", hp, np.array((s_ * 1.0, -0.3, 0)), (0, 0, 1), 0.018)
    p, n = kit.torso(sp2 + 0.0, math.pi)
    kit.box("Spine2", p + n * 0.04, n, (0, 0, 1), (0.085, 0.11, 0.03), 0.006)
    for k in range(3):
        kit.box("Spine2", p + n * 0.0555 + np.array((0, 0, 0.03 - 0.03 * k)), n, (0, 0, 1), (0.064, 0.006, 0.002), 0.0008, mat="Glow")
    p, n = kit.limb("LeftForeArm", 0.5, math.radians(-30), push=0.03)
    axf = nrm(L["LeftHand"] - L["LeftForeArm"])
    kit.plate("LeftForeArm", p, n, axf, 0.042, 0.052, offset=0.0, thickness=0.006, crown=0.004, chamfer=0.003, groove=0.0, segs=24,
              poly=hex_outline(), corner=0.12, mat_top="Screen", clearance=0.003, cast_r=0.1)
    emitter(kit, "LeftForeArm", p + n * 0.012, n, axf, 0.012)
    collar(kit, rows=1, height=0.024, push=0.012, segs=10)
    return suit


# ============================================================================= restored v2 definitions (override earlier ones)

def emitter(kit, key, center, n, up, r=0.024):
    nn = nrm(n)
    rr, u, _ = gear.frame_from(nn, up)
    part = kit.P(key)
    ring = np.array([center + (rr * math.cos(t) + u * math.sin(t)) * r for t in np.linspace(0, 2 * math.pi, 29)])
    tube(part, ring, 0.0055, 10, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0})
    tube(part, ring * 0 + np.array([center + (rr * math.cos(t) + u * math.sin(t)) * r * 0.72 + nn * 0.003 for t in np.linspace(0, 2 * math.pi, 29)]),
         0.0018, 6, mat="Glow2")
    verts = [center + nn * 0.004] + [center + nn * 0.002 + (rr * math.cos(t) + u * math.sin(t)) * r * 0.62 for t in np.linspace(0, 2 * math.pi, 6, endpoint=False)]
    part.add(np.array(verts), [[0, 1 + i, 1 + (i + 1) % 6] for i in range(6)], "Screen")
    tube(part, np.array([center - nn * 0.012, center]), r * 0.85, 12, mat="Armor", attrs={"plate": kit.next_id()}, caps=True)


def seam_strips(kit, mat="Glow", female=False):
    """Glowing seams in the panel gaps: sternum channel, abdominal gaps, spine channel."""
    L = kit.L
    hips, sp1, nk = L["Hips"][2], L["Spine1"][2], L["Neck"][2]
    kit.strip("suit", [kit.torso(z, 0.0, push=0.0)[0] for z in np.linspace(hips + 0.03, nk - 0.05, 10)], mat=mat, width=0.0035, height=0.002)
    kit.strip("suit", [kit.torso(z, math.pi, push=0.0)[0] for z in np.linspace(hips + 0.03, nk - 0.03, 10)], mat=mat, width=0.0035, height=0.002)


def set_vanguard_mk2(kit):
    """Heavy powered plate: thick sculpted chest / back / abdomen panels, layered pauldrons, chest reactor, gorget,
    back power pack, armoured limbs with knee/elbow caps, tassets; glowing seams in every panel gap."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.002))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    seam_strips(kit, "Glow")
    torso_panels(kit, rg, off=0.024, gap=0.008, rows_abs=2)
    for s_ in (1, -1):
        limb_panels(kit, rg, s_, arm_off=0.018, leg_off=0.02, cover=0.6)
    p, n = kit.torso(sp2 + 0.03, 0.0, R=0.4)
    reactor(kit, "Spine2", p + n * 0.04, n, (0, 0, 1), 0.032)
    # back power pack
    p, n = kit.torso(sp2 - 0.01, math.pi, R=0.4)
    r_, u_, n_ = kit.box("Spine2", p + n * 0.05, n, (0, 0, 1), (0.14, 0.18, 0.05), 0.008)
    for k in range(4):
        kit.box("Spine2", p + n * 0.0755 + u_ * (0.05 - k * 0.028), n, (0, 0, 1), (0.1, 0.006, 0.003), 0.001, mat="Glow")
    for s_ in (1, -1):
        c = p + n * 0.05 + r_ * s_ * 0.085
        tube(kit.P("Spine2"), np.array([c + u_ * 0.06, c - u_ * 0.075]), 0.018, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 1.0}, caps=True)
        tube(kit.P("Spine2"), np.array([c + u_ * 0.04 + n_ * 0.015, c - u_ * 0.055 + n_ * 0.015]), 0.0045, 8, mat="Glow2")
    collar(kit, rows=2, height=0.026, push=0.018, segs=10)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        pauldron(kit, s_, 1.12, layers=3, offset=0.03)
        joint_cap(kit, bu, bf, (s_ * 0.5, 0.6, -0.2), 0.032, 0.02)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.046, 0.026)
        for k, ph in enumerate((0.35, 1.05)):
            p, n = kit.torso(hips - 0.07, s_ * ph, R=0.4)
            kit.plate(bt, p, n, (0, 0, 1), 0.065 if k == 0 else 0.05, 0.065, offset=0.026, thickness=0.007, crown=0.005, chamfer=0.003,
                      n_exp=4.0, segs=28, groove=0.62, poly=[(-1, 1), (1, 1), (0.85, -0.7), (0.4, -1), (-0.4, -1), (-0.85, -0.7)], corner=0.2)
        kit.strip("suit", [kit.limb(bf, t, math.radians(150 * s_), push=0.0)[0] for t in np.linspace(0.1, 0.9, 7)], mat="Glow2")
    rows = gear.ring_band(ctx, kit.P("Hips"), [np.array((0, L["Hips"][1], hips + 0.02)), np.array((0, L["Hips"][1], hips - 0.025))],
                          lambda ph: np.array((math.sin(ph), -math.cos(ph), 0.0)), None, [0.02, 0.02], n=40, mat="Armor",
                          attrs={"plate": kit.next_id(), "wear": 0.3})
    p, n = kit.limb("LeftForeArm", 0.6, math.radians(-30), push=0.032)
    axf = nrm(L["LeftHand"] - L["LeftForeArm"])
    kit.box("LeftForeArm", p, n, axf, (0.036, 0.064, 0.012), 0.003)
    kit.box("LeftForeArm", p + n * 0.0062, n, axf, (0.028, 0.05, 0.002), 0.0008, mat="Screen")
    return suit


def set_aegis_exo(kit):
    """Exoskeleton frame over techwear: light chest/forearm/shin panels, vertebral spine column, shoulder yoke with
    actuator hubs, limb struts with glowing pistons, waist ring, cuffs."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0065, 0.004))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    torso_panels(kit, rg, off=0.019, gap=0.012, rows_abs=0, back=False)
    for s_ in (1, -1):
        limb_panels(kit, rg, s_, arm_off=0.016, leg_off=0.017, upper=False, thigh=False, cover=0.45)
    zs = np.linspace(hips + 0.02, nk - 0.01, 9)
    for k, z in enumerate(zs):
        p, n = kit.torso(z, math.pi, push=0.004, R=0.4)
        key = spine_key(kit, z)
        kit.box(key, p + n * 0.014, n, (0, 0, 1), (0.056 - 0.004 * (k % 2), 0.03, 0.022), 0.005)
        kit.box(key, p + n * 0.0255, n, (0, 0, 1), (0.02, 0.014, 0.002), 0.0008, mat="Glow")
    spine = np.array([kit.torso(z, math.pi, push=0.034)[0] for z in np.linspace(hips + 0.02, nk - 0.01, 14)])
    tube(kit.P("suit"), spine + np.array((0.016, 0, 0)), 0.005, 8, mat="Glow2")
    tube(kit.P("suit"), spine - np.array((0.016, 0, 0)), 0.005, 8, mat="Glow2")
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        sh = L[bu]
        yoke = [kit.torso(sp2 + 0.04, math.pi - s_ * 0.25, push=0.03)[0], sh + np.array((-s_ * 0.06, 0.04, 0.085)),
                sh + np.array((-s_ * 0.05, -0.055, 0.07)), kit.torso(sp2 + 0.06, s_ * 0.45, push=0.03)[0]]
        P_ = gear.catmull(yoke, 18)
        tube(kit.P("Spine2"), np.array(P_), 0.013, 12, mat="Armor", attrs={"plate": kit.next_id(), "wear": 0.6}, caps=True)
        d = nrm(np.array((s_ * 1.0, 0, 0.25)))
        hub(kit, bu, sh + d * 0.085, d, (0, 0, 1), 0.036)
        strut(kit, bu, bu, 0.15, 0.85, math.radians(-100 * s_), push=0.026, r=0.011)
        hub(kit, bf, L[bf] + nrm(np.array((s_ * 0.6, 0.6, 0.0))) * 0.058, nrm(np.array((s_ * 0.6, 0.6, 0.0))), (0, 0, 1), 0.026)
        strut(kit, bf, bf, 0.08, 0.86, math.radians(-115 * s_), push=0.024, r=0.009)
        cuff(kit, bf, bf, 0.9, 0.012, 0.026)
        hp = L[bt] + np.array((s_ * 0.115, 0.0, 0.0))
        hub(kit, "Hips", hp, np.array((s_ * 1.0, 0, 0)), (0, 0, 1), 0.04)
        strut(kit, bt, bt, 0.1, 0.86, math.radians(-90 if s_ > 0 else 90), push=0.028, r=0.012)
        kn = L[bs]
        hub(kit, bs, kn + np.array((s_ * 0.078, 0.0, 0.0)), np.array((s_ * 1.0, 0, 0)), (0, 0, 1), 0.032)
        strut(kit, bs, bs, 0.08, 0.74, math.radians(-90) if s_ > 0 else math.radians(90), push=0.026, r=0.01)
        cuff(kit, bs, bs, 0.76, 0.014, 0.028)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.04, 0.022)
        pauldron(kit, s_, 0.78, layers=1, offset=0.024)
    gear.ring_band(ctx, kit.P("Hips"), [np.array((0, L["Hips"][1], hips + 0.016)), np.array((0, L["Hips"][1], hips - 0.028))],
                   lambda ph: np.array((math.sin(ph), -math.cos(ph), 0.0)), None, [0.022, 0.022], n=40, mat="Armor",
                   attrs={"plate": kit.next_id(), "wear": 0.4})
    p, n = kit.torso(sp2 - 0.0, 0.0)
    kit.box("Spine2", p + n * 0.038, n, (0, 0, 1), (0.06, 0.07, 0.014), 0.004)
    kit.box("Spine2", p + n * 0.046, n, (0, 0, 1), (0.046, 0.054, 0.002), 0.001, mat="Screen")
    collar(kit, rows=1, height=0.028, push=0.016, segs=8)
    return suit


def stealth_panels(kit, female=False):
    ctx, L = kit.ctx, kit.L
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    R = rg.R
    tor = (R["torso"] + R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    # angular light-bending panels (Screen = active camo) with hard shells on the shoulders, shins and forearms
    for s_ in (1, -1):
        diag = (z - (sp1 + 0.02)) - 0.6 * (np.abs(x) - 0.05)
        m = tor & front & (x * s_ > 0.01) & (diag > 0.0) & (z < nk - 0.05) & (np.abs(x) < 0.17)
        panel(kit, f"camo_chest{s_}", m, 0.011, rim=0.004, mat="Armor")
        m = tor & front & (x * s_ > 0.012) & (diag < -0.012) & (z > hips + 0.04) & (np.abs(x) < 0.13)
        panel(kit, f"camo_abs{s_}", m, 0.009, rim=0.004, mat="Armor")
        m = tor & ~front & (x * s_ > 0.014) & (z > sp1 - 0.05) & (z < nk - 0.05) & (np.abs(x) < 0.15)
        panel(kit, f"camo_back{s_}", m, 0.01, rim=0.004, mat="Armor")
        bu, bf, bt, bs, bh = side_bones(s_)
        limb_panels(kit, rg, s_, arm_off=0.011, leg_off=0.012, cover=0.42, upper=True, thigh=True)
        pauldron(kit, s_, 0.7 if not female else 0.6, layers=1, offset=0.014)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.034, 0.014, groove=0.0)
        kit.strip("suit", [kit.torso(z_, s_ * 1.45, push=0.0)[0] for z_ in np.linspace(hips - 0.02, sp2 + 0.12, 8)])
        kit.strip("suit", [kit.limb(bt, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.08, 0.95, 7)] +
                  [kit.limb(bs, t, math.radians(-90 if s_ > 0 else 90), push=0.0)[0] for t in np.linspace(0.05, 0.75, 6)])
    seam_strips(kit, "Glow2")
    collar(kit, rows=2, height=0.022, push=0.012, segs=10)


def set_samurai_neo(kit):
    """Cyber-samurai: lamellar do (rows of scales laced with neon), sculpted muna-ita chest plate with reactor crest,
    large layered sode, kusazuri tassets, kote and suneate panels."""
    ctx, L = kit.ctx, kit.L
    suit = build_suit(kit, "suit", stock_offset(ctx, 0.0045, 0.002))
    rg = Region(ctx)
    hips, sp1, sp2, nk = L["Hips"][2], L["Spine1"][2], L["Spine2"][2], L["Neck"][2]
    x, y, z = rg.x, rg.y, rg.z
    tor = (rg.R["torso"] + rg.R["hips"] * 0.5) > 0.5
    front = y < rg.cy - 0.005
    # muna-ita: one sculpted upper chest plate, back plate
    panel(kit, "muna", tor & front & (z > sp2 - 0.0) & (z < nk - 0.04) & (np.abs(x) < 0.17), 0.03, rim=0.008)
    panel(kit, "senaka", tor & ~front & (z > sp2 - 0.03) & (z < nk - 0.04) & (np.abs(x) < 0.16), 0.026, rim=0.007)
    rows = np.linspace(hips + 0.035, sp2 - 0.02, 4)
    for r, zr in enumerate(rows):
        key = spine_key(kit, zr)
        for k in range(9):
            ph = -1.3 + 2.6 * (k + 0.5 * (r % 2)) / 9
            p, n = kit.torso(zr, ph)
            lamella(kit, key, p, n, (0, 0, 1), 0.023, 0.028, off=0.008 + 0.004 * r)
        for k in range(5):
            ph = math.pi - 0.8 + 1.6 * (k + 0.5 * (r % 2)) / 5
            p, n = kit.torso(zr, ph)
            lamella(kit, key, p, n, (0, 0, 1), 0.026, 0.028, off=0.008 + 0.004 * r)
        kit.strip(key, [kit.torso(zr + 0.027, ph, push=0.016 + 0.004 * r)[0] for ph in np.linspace(-1.3, 1.3, 10)], push=0.0, width=0.0026)
    p, n = kit.torso(sp2 + 0.05, 0.0)
    reactor(kit, "Spine2", p + n * 0.046, n, (0, 0, 1), 0.024)
    for s_ in (1, -1):
        bu, bf, bt, bs, bh = side_bones(s_)
        pauldron(kit, s_, 1.1, layers=4, offset=0.024)
        limb_panels(kit, rg, s_, arm_off=0.015, leg_off=0.017, upper=True, thigh=True, cover=0.5)
        cuff(kit, bf, bf, 0.93, 0.012, 0.016)
        for ph in (0.38, 0.95):
            for r in range(3):
                zz = hips - 0.035 - r * 0.048
                p, n = kit.torso(zz, s_ * ph, R=0.19)   # start inside the A-posed hands: hit the hip, not the forearm
                lamella(kit, bt, p, n, (0, 0, 1), 0.055, 0.025, off=0.024 + 0.005 * (2 - r), segs=16)
        joint_cap(kit, bt, bs, (0, -1, 0.05), 0.04, 0.024)
    for r in range(3):
        for k in range(3):
            p, n = kit.torso(hips - 0.03 - r * 0.048, math.pi + (k - 1) * 0.42, R=0.19)
            lamella(kit, "Hips", p, n, (0, 0, 1), 0.055, 0.025, off=0.024 + 0.005 * (2 - r), segs=16)
    collar(kit, rows=1, height=0.032, push=0.02, segs=10)
    return suit


SETS = {
    "kael": {"vanguard_mk2": ("Vanguard Mk II", set_vanguard_mk2), "aegis_exo": ("Aegis Exo-Frame", set_aegis_exo),
             "phantom_stealth": ("Phantom Stealth", set_phantom_stealth), "samurai_neo": ("Samurai Neo", set_samurai_neo)},
    "lyra": {"netrunner_x": ("Netrunner X", set_netrunner_x), "valkyrie": ("Valkyrie", set_valkyrie),
             "phantom_stealth_f": ("Phantom Stealth", set_phantom_stealth), "arc_sentinel": ("Arc Sentinel", set_arc_sentinel)},
}
LOOKS = {  # hue/value of the neutral BaseColor per set + suggested preview / catalog tints (pv_*)
    "vanguard_mk2": {"armor": "#7d838c", "suit": "#1d2026", "glow": "#00e5ff", "glow2": "#ff8a1f", "screen": "#38d8ff", "accent": "#ff8a1f", "value": 0.82, "pv_armor": "#9aa0a8", "pv_accent": "#2a2d33"},
    "aegis_exo": {"armor": "#4a4f57", "suit": "#3a3f36", "glow": "#00e5ff", "glow2": "#9dff3a", "screen": "#38d8ff", "accent": "#d6ff3a",
                  "paint_metal": 0.55, "paint_smooth": 0.6, "value": 0.7, "pv_armor": "#6e7468", "pv_accent": "#4d5243"},
    "phantom_stealth": {"armor": "#1c1f24", "suit": "#101215", "glow": "#00e5ff", "glow2": "#ff2bd6", "screen": "#2a6dff", "accent": "#2a6dff", "hex": True,
                        "paint_metal": 0.35, "paint_smooth": 0.35, "value": 0.38, "suit_value": 0.5, "pv_armor": "#5a5f68", "pv_accent": "#26282d"},
    "samurai_neo": {"armor": "#7a1f24", "suit": "#15161a", "glow": "#ff2bd6", "glow2": "#ffd040", "screen": "#ff5ad6", "accent": "#d8b25a", "value": 0.62, "pv_armor": "#b0453f", "pv_accent": "#24252a"},
    "netrunner_x": {"armor": "#d9dde3", "suit": "#1a1b22", "glow": "#ff2bd6", "glow2": "#8a5bff", "screen": "#ff5ae0", "accent": "#8a5bff",
                    "paint_smooth": 0.65, "value": 0.9, "pv_armor": "#d6d8de", "pv_accent": "#2a2433"},
    "valkyrie": {"armor": "#c9ccd2", "suit": "#24202e", "glow": "#8ad8ff", "glow2": "#ff2bd6", "screen": "#b79bff", "accent": "#d8b25a",
                 "paint_metal": 0.5, "paint_smooth": 0.7, "value": 0.88, "pv_armor": "#c8c4d4", "pv_accent": "#3a3346"},
    "phantom_stealth_f": {"armor": "#1c1f24", "suit": "#101215", "glow": "#ff2bd6", "glow2": "#8a5bff", "screen": "#7a3dff", "accent": "#7a3dff", "hex": True,
                          "paint_metal": 0.35, "paint_smooth": 0.35, "value": 0.38, "suit_value": 0.5, "pv_armor": "#5d5866", "pv_accent": "#26232c"},
    "arc_sentinel": {"armor": "#5d6676", "suit": "#1d1f27", "glow": "#62dcff", "glow2": "#ff2bd6", "screen": "#62dcff", "accent": "#62dcff", "value": 0.8, "pv_armor": "#7c8798", "pv_accent": "#262833"},
}


# ============================================================================= finalize / textures


def finalize(kit, suit):
    ctx = kit.ctx
    objs = []
    ctx.finalize(suit)
    objs.append(suit)
    for o, bone, wb in kit.shells:
        if bone:
            ctx.finalize(o, bone=bone)
        else:
            ctx.finalize(o, weight_bones=wb)
        objs.append(o)
    for key, part in kit.parts.items():
        if not part.F:
            continue
        o = part.build(max_edge=None)
        if key == "suit":
            ctx.finalize(o)
        elif isinstance(key, tuple):
            ctx.finalize(o, weight_bones=list(key))
        else:
            ctx.finalize(o, bone=key)
        objs.append(o)
    return objs


def drop_strays(obj, body, limit=0.17):
    """Safety net: delete connected pieces that reach further than `limit` from the body (mis-cast plates)."""
    import bmesh
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons([v.co.copy() for v in body.data.vertices], [list(p.vertices) for p in body.data.polygons])
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    far = set()
    for v in bm.verts:
        hit, n, fi, d = tree.find_nearest(v.co, 1.0)
        if d is not None and d > limit:
            far.add(v.index)
    if not far:
        bm.free(); return 0
    seen, kill = set(), []
    for vi in far:
        if vi in seen:
            continue
        stack, island = [bm.verts[vi]], []
        while stack:
            v = stack.pop()
            if v.index in seen:
                continue
            seen.add(v.index); island.append(v)
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in seen:
                    stack.append(o)
        kill += island
    n = len(kill)
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(obj.data); bm.free(); obj.data.update()
    C.log("dropped stray pieces, verts", n)
    return n


def fill_weights(obj):
    """Vertices left without skin weights (e.g. limited-bone parts outside those bones' influence) copy the weights
    of the nearest weighted vertex."""
    from mathutils.kdtree import KDTree
    me = obj.data
    wv = [v.index for v in me.vertices if any(g.weight > 1e-4 for g in v.groups)]
    un = [v.index for v in me.vertices if not any(g.weight > 1e-4 for g in v.groups)]
    if not un:
        return 0
    kd = KDTree(len(wv))
    for i in wv:
        kd.insert(me.vertices[i].co, i)
    kd.balance()
    for i in un:
        _, j, _ = kd.find(me.vertices[i].co)
        for g in me.vertices[j].groups:
            if g.weight > 1e-4:
                obj.vertex_groups[g.group].add([i], g.weight, "REPLACE")
    return len(un)


def unify_slots(obj):
    me = obj.data
    have = [m.name if m else "" for m in me.materials]
    idx = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", idx)
    names = np.array([have[i] if i < len(have) else "Armor" for i in idx])
    remap = {"Metal": "Armor", "Gloves": "SuitSecondary", "Belt": "SuitSecondary", "Garment_Top": "SuitSecondary"}
    names = np.array([remap.get(n, n) for n in names])
    me.materials.clear()
    for n in SLOTS:
        me.materials.append(gear.get_mat(n))
    me.polygons.foreach_set("material_index", np.array([SLOTS.index(n) if n in SLOTS else 0 for n in names], np.int32))


def neutral(hexcol, value, sat):
    """BaseColor (sRGB 0..1) for a slot Unity multiplies with the appearance colour: luminance `value`, hue of hexcol
    kept at `sat` saturation."""
    c = C.hx(hexcol)
    lum = float(c @ np.array((0.3, 0.59, 0.11)))
    g = np.full(3, lum)
    c = g + (c - g) * sat
    return np.clip(c / max(float(c @ np.array((0.3, 0.59, 0.11))), 1e-3) * value, 0, 1)


def paint_armor(t, ao, look, seed=1.0):
    P = t["P"]; A = t["A"]
    n = len(P)
    wear, cav, plate_id = A["wear"], A["cavity"], A["plate"]
    lx, ly = A["lx"], A["ly"]
    h = np.zeros(n, np.float32)
    chips = np.clip(ss(0.45, 0.95, wear) * (0.55 + 0.6 * TB.fbm3(P, 260.0, 3, seed)) - 0.35, 0, 1) * 1.6
    scr = np.zeros(n)
    for k in range(3):
        ang = TB.hash3(np.stack([plate_id, plate_id * 0 + k, plate_id * 0], -1), 3.0 + k) * math.pi
        u = lx * math.cos(1.0) + ly * math.sin(1.0)
        v = -lx * np.sin(ang) + ly * np.cos(ang)
        line = np.abs(((v + TB.hash3(np.stack([plate_id, plate_id, plate_id * 0 + k], -1), 9.0) * 0.1) % 0.023) - 0.0115)
        scr = np.maximum(scr, (line < 0.00025) * (TB.vnoise3(P, 90.0, 4.0 + k) > 0.62))
    # panel line insets and small vents on larger plates
    pid = np.round(plate_id).astype(int)
    vents = np.zeros(n)
    lines = np.zeros(n)
    hsh = TB.hash3(np.stack([pid * 1.0, pid * 0.0, pid * 0.0], -1), 11.0)
    for k in range(3):
        cx = -0.02 + 0.012 * k
        d = np.maximum(np.abs(lx - cx) - 0.0022, np.abs(ly + 0.03) - 0.01)
        vents = np.maximum(vents, (hsh > 0.6) * (1 - ss(-0.0004, 0.0004, d)))
    dl = np.abs(ly - 0.25 * lx - (hsh - 0.5) * 0.03)
    lines = (hsh < 0.45) * (1 - ss(0.0005, 0.0009, dl)) * (np.abs(lx) < 0.05)
    stripe = (hsh > 0.82) * (np.sin((lx + ly) / 0.006 * math.pi) > 0.25) * (lx > 0.02) * (ly > 0.015) * (lx < 0.06) * (ly < 0.045)
    hexc = np.zeros(n)
    if look.get("hex"):
        # light-bending cells: hexagonal micro-facets (height + angle-dependent tint baked as value variation)
        q = np.stack([A["bx"], A["by"], A["bz"]], 1) if "bx" in A else P
        u_ = q[:, 0] / 0.012 + q[:, 1] / 0.012 * 0.3
        v_ = q[:, 2] / 0.012
        hx_ = np.stack([u_ - v_ * 0.5, v_ * 0.866], 1)
        cell = np.round(hx_)
        d = np.abs(hx_ - cell).max(1)
        hexc = ss(0.38, 0.47, d)
        h += -0.00035 * hexc + 0.00008 * TB.hash3(np.stack([cell[:, 0], cell[:, 1], cell[:, 0] * 0], -1), 2.0)
        lines = np.maximum(lines, hexc * 0.6)
    h -= 0.001 * vents + 0.0005 * lines + 0.00012 * scr + 0.0005 * cav
    h += 0.00003 * TB.fbm3(P, 500.0, 2, 5.0)
    paint = np.clip(1 - chips - scr * 0.7, 0, 1)
    pc = neutral(look["armor"], look.get("value", 0.86), 0.45)
    base = 0.92 + 0.06 * TB.fbm3(P, 40.0, 3, seed + 1)
    metal = 0.62 + 0.1 * TB.fbm3(P, 200.0, 2, 4.0)
    grime = np.clip((1 - ao) * 1.2 + cav * 0.5, 0, 1) * (0.5 + 0.5 * TB.fbm3(P, 30.0, 2, 7.0))
    acc = C.srgb2lin(C.hx(look.get("accent", look["glow2"]))) ** (1 / 2.2)
    col = (paint[:, None] * (base[:, None] * pc[None] * (1 - stripe[:, None]) + stripe[:, None] * acc[None] * 0.9) +
           (1 - paint[:, None]) * metal[:, None] * np.array((0.95, 0.96, 0.98)))
    col = col * (1 - 0.4 * grime[:, None]) * (1 - 0.55 * vents[:, None]) * (1 - 0.35 * lines[:, None])
    metallic = np.clip((1 - paint) * 0.95 + paint * look.get("paint_metal", 0.25), 0, 1)
    smooth = paint * (look.get("paint_smooth", 0.55) - 0.2 * grime) + (1 - paint) * (0.7 - 0.25 * grime)
    return np.clip(col, 0, 1), h, metallic, smooth, paint


def paint_suit(t, ao, look, seed=2.0):
    P = t["P"]; A = t["A"]
    n = len(P)
    bp = np.stack([A["bx"], A["by"], A["bz"]], 1) if "bx" in A else P
    # weave micro relief + quilted / ribbed panels from a coarse cell layout in body space
    weave = 0.5 + 0.5 * np.sin(bp[:, 0] * 2400) * np.sin(bp[:, 2] * 2400)
    f1 = TB.worley3(bp * np.array((1.0, 1.0, 0.6)), 9.0, seed)
    q = np.floor(bp * 9.0)
    seam = np.zeros(n)
    try:
        f2 = TB.worley3(bp * np.array((1.0, 1.0, 0.6)) + 0.031, 9.0, seed)
    except Exception:
        f2 = f1
    cellb = np.abs(np.sin(bp[:, 2] * 38.0 + 1.3 * np.sin(bp[:, 0] * 11.0))) < 0.05
    cellv = np.abs(np.sin(bp[:, 0] * 31.0 + 0.8 * np.sin(bp[:, 2] * 7.0))) < 0.04
    seam = np.clip(cellb * 1.0 + cellv * (np.abs(bp[:, 0]) < 0.2) * 1.0, 0, 1)
    rib = 0.5 + 0.5 * np.sin(bp[:, 2] * 900.0)
    ribz = (TB.vnoise3(bp, 6.0, seed + 3) > 0.55)
    h = 0.00006 * weave - 0.0007 * seam + 0.00025 * rib * ribz + 0.00012 * TB.fbm3(bp, 60.0, 3, seed)
    sc = neutral(look["suit"], look.get("suit_value", 0.8), 0.3)
    v = (0.92 + 0.08 * weave) * (1 - 0.3 * seam) * (0.9 + 0.1 * TB.fbm3(bp, 25.0, 2, seed + 5))
    v = v * (0.75 + 0.25 * ao) * 1.35
    col = v[:, None] * sc[None] * 1.0
    metallic = np.zeros(n) + 0.02
    smooth = 0.32 + 0.12 * ribz - 0.1 * seam
    paint = np.ones(n)
    return np.clip(col, 0, 1), h, metallic, smooth, paint


def atlas(obj, mat, fn, look, size, base, label, samples=16):
    objs = [obj]
    if TB._faces_with(obj, mat) is None:
        return None
    TB.pack(objs, mat, margin=0.003)
    ao = TB.bake_ao(objs, mat, size, samples=samples, distance=0.05, hide=[o for o in bpy.data.objects if o.type == "MESH" and o is not obj])
    T = TB.raster(objs, mat, size)
    t = texstage.subset(T)
    ao_t = ao.reshape(-1)[t["idx"]]
    rgb, h, metal, smooth, paint = fn(t, ao_t, look)
    Cimg = texstage.finish(T, texstage.full(T, t, rgb))
    Nm = texstage.to_normal(T, t, h)
    MM = texstage.finish(T, texstage.full(T, t, np.stack([metal, np.clip(ao_t * 0.8 + 0.2, 0, 1), paint, smooth], 1)))
    files = [f"{base}_{label}_BaseColor.png", f"{base}_{label}_Normal.png", f"{base}_{label}_MaskMap.png"]
    C.write_png(Cimg, os.path.join(TEX_DIR, files[0]), "RGB")
    C.write_png(Nm, os.path.join(TEX_DIR, files[1]), "RGB")
    C.write_png(MM, os.path.join(TEX_DIR, files[2]), "RGBA")
    return files


PREVIEW_TINT = {"kael": {"armor": "#a9a59a", "accent": "#3a3d42", "glow": "#00e5ff", "glow2": "#ff2bd6"},
                "lyra": {"armor": "#8f8999", "accent": "#3a3346", "glow": "#ff2bd6", "glow2": "#8a5bff"}}


def preview_mats(obj, look, files_a, files_s, cid="kael"):
    """Mirror of the Unity runtime: Armor x appearance armour colour, SuitSecondary x accent, glows from the
    appearance glow colours (preview uses each set's suggested colours where given)."""
    pt = dict(PREVIEW_TINT[cid])
    for k in ("armor", "accent", "glow", "glow2"):
        if look.get("pv_" + k):
            pt[k] = look["pv_" + k]
    mats = {}
    if files_a:
        mats["Armor"] = texstage.preview_mat("pv_Armor_" + obj.name, os.path.join(TEX_DIR, files_a[0]), os.path.join(TEX_DIR, files_a[1]),
                                             maskmap=os.path.join(TEX_DIR, files_a[2]), tint=tuple(C.hx(pt["armor"])))
    if files_s:
        mats["SuitSecondary"] = texstage.preview_mat("pv_Suit_" + obj.name, os.path.join(TEX_DIR, files_s[0]), os.path.join(TEX_DIR, files_s[1]),
                                                     maskmap=os.path.join(TEX_DIR, files_s[2]), tint=tuple(C.hx(pt["accent"])))
    mats["Glow"] = studio.flat("pv_Glow_" + obj.name, pt["glow"], 0.3, 0, (pt["glow"], 8.0))
    mats["Glow2"] = studio.flat("pv_Glow2_" + obj.name, pt["glow2"], 0.3, 0, (pt["glow2"], 8.0))
    mats["Screen"] = studio.flat("pv_Screen_" + obj.name, "#06141a", 0.15, 0, (pt["glow"], 2.0))
    for i, m in enumerate(obj.data.materials):
        if m and m.name in mats:
            obj.data.materials[i] = mats[m.name]


def restore(obj):
    for i, m in enumerate(obj.data.materials):
        obj.data.materials[i] = gear.get_mat(SLOTS[i])


def main():
    a = C.args()
    cid = a[0]
    table = SETS[cid]
    sel = a[1].split(",") if len(a) > 1 and not a[1].startswith("--") else list(table)
    os.makedirs(TEX_DIR, exist_ok=True); os.makedirs(PREV_DIR, exist_ok=True); os.makedirs(THUMB_DIR, exist_ok=True)
    os.makedirs(os.path.join(C.CACHE, "catalog", "armour"), exist_ok=True)
    for sid in sel:
        t0 = time.time()
        rig, body = C.load_ref(cid)
        ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
        kit = Kit(ctx, cid)
        label, fn = table[sid]
        look = LOOKS[sid]
        suit = fn(kit)
        objs = finalize(kit, suit)
        obj = gear.join(objs, f"{cid}_{sid}")
        unify_slots(obj)
        drop_strays(obj, body)
        fill_weights(obj)
        ntri = C.tris(obj)
        C.log(sid, "tris", ntri, "verts", len(obj.data.vertices), "shapes", len(obj.data.shape_keys.key_blocks) - 1 if obj.data.shape_keys else 0,
              "build s", round(time.time() - t0, 1))
        base = f"{cid}_{sid}"
        fa = fs = None
        if "--no-tex" not in a:
            fa = atlas(obj, "Armor", paint_armor, look, 2048, base, "Armor")
            fs = atlas(obj, "SuitSecondary", paint_suit, look, 2048, base, "Suit")
            C.log(sid, "textures", round(time.time() - t0, 1))
        # previews
        obj["custom"] = 1
        studio.hero_materials(cid, hide_outfit=True, keep=KEEPS[cid])
        obj.hide_render = False; obj.hide_viewport = False
        import hair_preview
        hair = hair_preview.load_default_hair(cid)
        preview_mats(obj, look, fa, fs, cid)
        H_ = float(max(C.get_co(body)[:, 2]))
        aim = Vector((0, 0, H_ * 0.53))
        studio.world_and_lights(aim, 2.2, rim=1.0, yaw=30)
        studio.camera(studio.view(aim, 30, 4, 4.6 * H_ / 1.85), aim, 50)
        thumb = os.path.join(THUMB_DIR, f"armour_{cid}_{sid}.png")
        studio.render(thumb, 512, 256)
        for tag, yaw, pitch, dist, aimz, lens in (("front", 0, 3, 4.4, 0.53, 50), ("q34", 35, 4, 4.4, 0.53, 50), ("back", 180, 4, 4.4, 0.53, 50),
                                                  ("chest", 25, 3, 1.5, 0.76, 50)):
            ai = Vector((0, 0, H_ * aimz))
            studio.world_and_lights(ai, 2.2 if tag != "chest" else 1.0, rim=1.0, yaw=yaw)
            studio.camera(studio.view(ai, yaw, pitch, dist * H_ / 1.85), ai, lens)
            studio.render(os.path.join(PREV_DIR, f"{cid}_{sid}_{tag}.png"), 640)
        restore(obj)
        if hair:
            bpy.data.objects.remove(hair, do_unlink=True)
        if "--no-export" not in a:
            path = os.path.join(OUT_DIR, f"{cid}_{sid}.fbx")
            for m in obj.modifiers:
                if m.type == "ARMATURE":
                    m.object = rig
            C.export_fbx(path, [obj], armature=rig)
            e = {"id": sid, "label": label, "hero": cid, "file": f"Armour/{cid}_{sid}", "kind": "skinned", "replaces": REPLACES[cid],
                 "keeps": KEEPS[cid], "thumb": f"Thumbs/armour_{cid}_{sid}", "tris": ntri,
                 "blendShapes": [k.name for k in obj.data.shape_keys.key_blocks[1:]] if obj.data.shape_keys else [],
                 "materials": {
                     "Armor": {"baseMap": f"Armour/Textures/{base}_Armor_BaseColor", "normal": f"Armour/Textures/{base}_Armor_Normal",
                               "maskMap": f"Armour/Textures/{base}_Armor_MaskMap", "tint": look.get("pv_armor", "#ffffff")},
                     "SuitSecondary": {"baseMap": f"Armour/Textures/{base}_Suit_BaseColor", "normal": f"Armour/Textures/{base}_Suit_Normal",
                                       "maskMap": f"Armour/Textures/{base}_Suit_MaskMap", "tint": look.get("pv_accent", "#ffffff")},
                     "Glow": {"color": look["glow"], "intensity": 4.0}, "Glow2": {"color": look["glow2"], "intensity": 4.0},
                     "Screen": {"color": look["screen"], "intensity": 1.5}},
                 "maskMapLayout": "R metallic, G occlusion, B paint mask, A smoothness"}
            with open(os.path.join(C.CACHE, "catalog", "armour", f"{cid}_{sid}.json"), "w") as f:
                json.dump(e, f, indent=1)
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.CACHE, f"armour_{cid}_{sid}.blend"), compress=True)
        C.log(sid, "done", round(time.time() - t0, 1))
    import catalog
    catalog.merge()


if __name__ == "__main__":
    main()
