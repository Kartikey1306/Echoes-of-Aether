"""Kael Voss v3 outfit (master concept dreamlayer/characters/kael/kael_master_front.png, used as a visual reference only):
quilted graphite bomber jacket (open front, high stand collar, left sleeve, sleeveless on the interface arm) over a
black plate carrier with a three-pouch placard, olive undersuit with a ribbed turtleneck, loose olive cargo trousers
with panel seams and real cargo pockets, large knee pads with magenta light, tall armoured boots with cyan/magenta
light strips and laces, segmented pauldrons with hinge brackets, knuckle-stud gloves, right-forearm Aether interface.

Builds on outfit_k2 (same helpers, mesh names and material slots); new material slot: Cloth_Jacket.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
import kcommon as K
from kcommon import ss, nrm
import garment as G
import meshops
import gear
import outfit_k2 as O2
from outfit_k2 import Outfit, GearCtx, surf, ring_points, band_mesh, limb_t, select_faces

PRE = K.PRE

# large flat panels (placard, cargo pockets, greaves) have edges longer than gear.Part's 13 cm stray-face guard
if not hasattr(gear, "_k3_orig_build"):
    gear._k3_orig_build = gear.Part.build


def _build(self, mat_order=None, max_edge=0.32):
    return gear._k3_orig_build(self, mat_order, max_edge)


gear.Part.build = _build

TORSO_B = ["Hips", "Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "LeftBreast", "RightBreast"]
# concept: the Aether interface (holographic sleeve) is on his LEFT forearm (viewer's right); the jacket is sleeveless
# on that side, the black jacket sleeve with the magenta stripe is on his right arm
IFACE, SLEEVE = "Left", "Right"
IS = 1.0 if IFACE == "Left" else -1.0          # +x = character's left
ARM_B = {s: [s + n for n in ("Arm", "ArmTwist", "ForeArm", "ForeArmTwist")] for s in ("Left", "Right")}


# ============================================================================= jacket geometry fields (shared with the bake)


def jacket_gap(z):
    """Half-width of the open front at height z (the plate carrier shows between the jacket fronts)."""
    return np.interp(z, [1.0, 1.08, 1.2, 1.32, 1.42, 1.5, 1.56, 1.62], [0.125, 0.124, 0.12, 0.112, 0.104, 0.096, 0.088, 0.084])


JK_HEM_F, JK_HEM_B = 1.03, 1.018          # concept: the bomber's ribbed hem sits at the top of the hips
BOOT_TOP_F, BOOT_TOP_B = 0.515, 0.48      # tall boot shaft top (front / back), just under the knee cap
TROUSER_END = 0.40                        # trousers end inside the boot shaft (hidden)
TROUSER_IN_BOOT = 0.0045                  # trouser offset inside the shaft (the shaft sits ~15 mm off the leg)
COLLAR_TOP = 0.112           # collar top above the jacket neckline (front); +0.04 at the back
JK_NECK = 1.548          # replaced at build time from the Neck bone (jacket())


def jk_hem(y):
    return JK_HEM_F + (JK_HEM_B - JK_HEM_F) * ss(-0.04, 0.06, y)


def decimate_masked(o, ratio, mask):
    """Collapse-decimate only the vertices where mask is True (cloth shells), keeping hard-surface details intact."""
    vg = o.vertex_groups.new(name="k_dec")
    idx = [int(i) for i in np.where(mask)[0]]
    if idx:
        vg.add(idx, 1.0, "REPLACE")
    m = o.modifiers.new("dec", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = ratio
    m.vertex_group = vg.name
    m.use_collapse_triangulate = False
    n0 = len(o.data.polygons)
    gear.apply_modifiers(o)
    o.vertex_groups.remove(o.vertex_groups["k_dec"])
    K.log("DECIMATE", o.name, n0, "->", len(o.data.polygons))


def _attr(o, name):
    a = o.data.attributes.get(name)
    v = np.zeros(len(o.data.vertices))
    if a is not None and a.domain == "POINT":
        a.data.foreach_get("value", v)
    return v


# ============================================================================= UVs: sewing-pattern panels


def panel_unwrap(o, fields):
    """Replace the MakeHuman-derived seams with garment panel seams and unwrap conformally: every face is labelled by
    the signs of the fields at its centre; edges between faces with different labels become seams (low distortion,
    even texel density, seams where a tailor would put them)."""
    me = o.data
    co = K.get_co(o)
    cen = np.array([co[list(p.vertices)].mean(0) for p in me.polygons])
    lab = np.zeros(len(cen), np.int64)
    for k, f in enumerate(fields):
        lab |= (np.asarray(f(cen)) > 0).astype(np.int64) << k
    ek = {}
    for p in me.polygons:
        for e in p.edge_keys:
            ek.setdefault(e, []).append(p.index)
    lookup = {tuple(sorted(e.vertices)): e.index for e in me.edges}
    seam = np.zeros(len(me.edges), bool)
    for e, fl in ek.items():
        if len(fl) == 2 and lab[fl[0]] != lab[fl[1]]:
            seam[lookup[tuple(sorted(e))]] = True
    me.edges.foreach_set("use_seam", seam)
    G.unwrap(o)
    return int(seam.sum())


def _front_back(P):
    return P[:, 1] - 0.012


def _split_with_sleeves(L):
    """Front/back plane on the torso; on the arms a vertical plane through each limb segment's axis (sleeve seams run
    along the top and the underside of the arm, so even the forward-swung forearm is cut into two halves)."""
    def f(P):
        out = P[:, 1] - 0.012
        for side, S in ((1, "Left"), (-1, "Right")):
            sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
            on = (P[:, 0] * side > 0.17)
            for a_, b_ in ((sh, el), (el, wr)):
                t, r = limb_t(P, a_, b_)
                d = nrm(b_ - a_)
                w = nrm(np.cross(d, np.array((0, 0, 1.0))))
                m = on & (t > (-0.02 if a_ is sh else 0.0)) & (t < (1.0 if a_ is sh else 1.1)) & (r < 0.14)
                out = np.where(m, (P - a_) @ w, out)
        return out
    return f


# ============================================================================= base layer: olive undersuit with a turtleneck


def top(self):
    B, L, T = self.B, self.L, self.T
    wb = lambda W, names: B.wsum(W, names)

    def pred(C, W):
        t = wb(W, TORSO_B + ARM_B["Left"] + ARM_B["Right"])
        hand = wb(W, ["LeftHand", "RightHand"])
        head = wb(W, ["Head"])
        return (t + wb(W, ["Neck"]) > 0.45) & (hand < 0.5) & (head < 0.35) & (C[:, 2] > 0.9)
    o = G.shell_from_faces(B, select_faces(B, pred), "Top")
    neck_c = np.array((0.0, -0.012))

    def f_hem(P):
        return P[:, 2] - (0.985 - 0.035 * ss(-0.04, 0.06, P[:, 1]))

    def f_neck(P):
        # ribbed turtleneck: up the neck to just under the jaw line (lower at the front)
        r = np.hypot(P[:, 0] - neck_c[0], (P[:, 1] - neck_c[1]) * 1.1)
        line = 1.628 + 0.03 * ss(-0.06, 0.05, P[:, 1])
        return np.maximum(line - P[:, 2], r - 0.095)

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
        o_ = np.full(len(P), 0.0085)
        z = P[:, 2]
        o_ += 0.0025 * (P[:, 0] * IS > 0.2)                                       # fuller sleeve on the interface arm
        neck = ss(1.57, 1.6, z)
        o_ = o_ * (1 - neck) + 0.0055 * neck                                     # turtleneck hugs the neck
        o_ += 0.002 * ss(1.0, 1.15, z) * (np.abs(P[:, 0]) < 0.2) * (1 - neck)
        for s in ("Left", "Right"):
            t, r = limb_t(P, L[s + "ForeArm"], L[s + "Hand"])
            m = (r < 0.1) & (np.sign(P[:, 0]) == np.sign(L[s + "Hand"][0]))
            o_ = np.where(m & (t > 0.0), o_ - 0.0012 + 0.0025 * ss(0.65, 0.9, t), o_)
        return o_
    G.relax_offset(o, B, off, iters=22, lam=0.5)
    G.rim(o, 0.0045)
    G.smooth_shading(o)
    G.set_material(o, "Garment_Top")
    arm_l = lambda P: np.where(P[:, 0] > 0.14, limb_t(P, L["LeftArm"], L["LeftForeArm"])[0] - 0.04, 1.0)
    arm_r = lambda P: np.where(P[:, 0] < -0.14, limb_t(P, L["RightArm"], L["RightForeArm"])[0] - 0.04, 1.0)
    panel_unwrap(o, [_split_with_sleeves(L), arm_l, arm_r, lambda P: P[:, 2] - 1.561])
    self.objs["Top"] = o
    B.push_layer(o)
    return o


# ============================================================================= quilted bomber jacket


def jacket(self):
    B, L = self.B, self.L
    global JK_NECK
    JK_NECK = float(L["Neck"][2]) - 0.052
    wb = lambda W, names: B.wsum(W, names)

    def pred(C, W):
        t = wb(W, TORSO_B + ARM_B["Left"] + ARM_B["Right"] + ["Neck"])
        hand = wb(W, ["LeftHand", "RightHand"])
        head = wb(W, ["Head"])
        return (t > 0.45) & (hand < 0.5) & (head < 0.2) & (C[:, 2] > 0.95)
    o = G.shell_from_faces(B, select_faces(B, pred), "Jacket")
    neck_c = np.array((0.0, -0.012))
    RA, RF = L[IFACE + "Arm"], L[IFACE + "ForeArm"]

    def f_hem(P):
        return P[:, 2] - jk_hem(P[:, 1])

    def f_neck(P):
        r = np.hypot(P[:, 0] - neck_c[0], (P[:, 1] - neck_c[1]) * 1.15)
        line = JK_NECK + 0.036 * ss(-0.06, 0.05, P[:, 1])
        return np.maximum(line - P[:, 2], r - 0.088)

    def f_front(P):
        front = ss(-0.035, -0.06, P[:, 1])
        return np.where(front > 0.5, np.abs(P[:, 0]) - jacket_gap(P[:, 2]), 1.0)

    def f_arms(P):
        out = np.full(len(P), 1.0)
        # interface arm: sleeveless, armhole just past the shoulder joint
        t, r = limb_t(P, RA, RF)
        m = (P[:, 0] * IS > 0.12)
        out = np.where(m, np.maximum(0.035 - t, r - 0.112), out)
        # jacket sleeve: to the glove cuff
        t, r = limb_t(P, L[SLEEVE + "ForeArm"], L[SLEEVE + "Hand"])
        m = (t > 0.4) & (r < 0.09) & (P[:, 0] * IS < 0)
        out = np.where(m, np.minimum(out, 0.88 - t), out)
        return out
    for f in (f_hem, f_neck, f_front, f_arms):
        G.cut(o, f)
    G.drop_islands(o, 20)

    def off(P, N):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        hz = jk_hem(y)
        o_ = np.full(len(P), 0.0145)
        o_ += 0.0065 * ss(1.15, 1.3, z) * (1 - ss(1.5, 1.56, z))                     # quilted chest panels are puffy
        o_ += 0.01 * ss(1.26, 1.12, z) * ss(hz + 0.03, hz + 0.08, z)                # roomy bomber body bloused over the hem
        o_ -= 0.003 * ss(hz + 0.05, hz + 0.02, z)                                   # snug ribbed hem band
        sl = (P[:, 0] * -IS > 0.2)
        o_ = np.where(sl, 0.0145, o_)                                               # bomber sleeve: roomy, follows the arm
        t2, r2 = limb_t(P, L[SLEEVE + "ForeArm"], L[SLEEVE + "Hand"])
        cuff = (P[:, 0] * -IS > 0.3) & (t2 > 0.7)
        o_ = np.where(cuff, o_ - 0.004 * ss(0.72, 0.84, t2), o_)
        return o_
    G.relax_offset(o, B, off, iters=18, lam=0.45)
    G.rim(o, 0.0065)
    G.smooth_shading(o)
    G.set_material(o, "Cloth_Jacket")
    arm_s = lambda P: np.where(P[:, 0] * -IS > 0.14, limb_t(P, L[SLEEVE + "Arm"], L[SLEEVE + "ForeArm"])[0] - 0.04, 1.0)
    panel_unwrap(o, [_split_with_sleeves(L), arm_s])
    self.objs["Jacket"] = o
    B.push_layer(o)
    # magenta light pipe on the sleeve's upper arm (concept), riding on the sleeve
    ctx = GearCtx(B)
    lp = gear.Part("JacketLight")
    sh, el = L[SLEEVE + "Arm"], L[SLEEVE + "ForeArm"]
    du = nrm(el - sh)
    ov = np.array((-IS * 1.0, -0.35, 0.3))
    outv = nrm(ov - du * (ov @ du))
    pts, nrs = [], []
    for tt in np.linspace(0.42, 0.58, 8):
        c = sh + (el - sh) * tt
        hit, hn = surf(ctx, c, outv, 0.2)
        if hit is not None:
            pts.append(hit + hn * 0.0004); nrs.append(hn)
    if len(pts) > 3:
        gear.light_strip(lp, np.array(pts), np.array(nrs), width=0.0042, height=0.0016, mat="Glow2")
    lo = lp.build()
    self.objs["Jacket"] = gear.join([o, lo], "Jacket")
    B._outer = None
    # base layer under the jacket: drop the faces the jacket fully covers (keeps the turtleneck, the interface sleeve
    # and the strip between the jacket fronts)
    top_o = self.objs.get("Top")
    if top_o is not None:
        n_kill = gear.strip_occluded(top_o, [o], dist=0.06, erode=2)
        K.log("STRIP Top under Jacket", n_kill)
    return self.objs["Jacket"]


def collar(self):
    """High stand collar of the jacket, sewn to the jacket neckline: open V at the front, standing up beside the jaw and
    taller at the back, leaning away from the neck towards its folded top edge."""
    B, L = self.B, self.L
    jk = self.objs["Jacket"]
    from mathutils.bvhtree import BVHTree
    jtree = BVHTree.FromPolygons([jk.matrix_world @ v.co for v in jk.data.vertices], [list(p.vertices) for p in jk.data.polygons])
    c0 = np.array((0.0, -0.014, 0.0))
    n = 72
    back = lambda ph: 0.5 - 0.5 * np.cos(ph)
    rows = []
    heights = [0.0, 0.12, 0.28, 0.46, 0.64, 0.82, 0.94, 1.0]
    for hk in heights:
        a0 = 40 - 12 * hk
        phis = np.radians(np.linspace(a0, 360 - a0, n))
        row = []
        for ph in phis:
            d = np.array((math.sin(ph), -math.cos(ph), 0.0))
            zb = JK_NECK + 0.036 * ss(-0.06, 0.05, c0[1] - 0.088 * math.cos(ph)) - 0.004
            cb = np.array((c0[0], c0[1], zb))
            hit = jtree.ray_cast(Vector(cb + d * 0.2), Vector(-d), 0.21)[0]
            rb = np.linalg.norm((np.array(hit) - cb)[:2]) if hit is not None else 0.088
            rb = min(max(rb, 0.068), 0.088)
            zt = JK_NECK + 0.112 + 0.04 * back(ph) - 0.008 * (1 - back(ph)) ** 2
            z = zb + (zt - zb) * hk
            # neck radius at this height (body only) + clearance; the collar leans out towards the top
            cz = np.array((c0[0], c0[1], z))
            hb = B.tree.ray_cast(Vector(cz + d * 0.11), Vector(-d), 0.12)[0]
            rn = np.linalg.norm((np.array(hb) - cz)[:2]) if hb is not None else 0.06
            rn = min(rn, 0.075)
            r = min(max(rb + 0.004 * hk + 0.012 * hk ** 2, rn + 0.012 + 0.008 * hk), 0.105)
            row.append(cz + d * r)
        rows.append(np.array(row))
    part = band_mesh("Collar", rows, "Cloth_Jacket", closed=False, uv_scale=3.0)
    o = part.build()
    sol = o.modifiers.new("sol", "SOLIDIFY")
    sol.thickness = 0.007
    sol.offset = 1.0
    sol.use_even_offset = True
    gear.apply_modifiers(o)
    G.smooth_shading(o)
    self.objs["Collar"] = o
    B.push_layer(o)
    return o


Outfit.top = top
Outfit.jacket = jacket
Outfit.collar = collar


# ============================================================================= plate carrier + chest plate


def chest_rig(self):
    """Black plate carrier: front/back panels, shoulder straps, cummerbund (Cloth_Gear), three-pouch placard."""
    B, L = self.B, self.L
    torso_b = ["Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "LeftBreast", "RightBreast", "Neck"]
    arm_b = ARM_B["Left"] + ARM_B["Right"]

    def pred(C, W):
        return (B.wsum(W, torso_b) > 0.4) & (B.wsum(W, arm_b) < 0.35) & (C[:, 2] > 1.1) & (C[:, 2] < 1.64) & (B.wsum(W, ["Head"]) < 0.1)
    o = G.shell_from_faces(B, select_faces(B, pred), "ChestRig")

    def field(P):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        top_f = 1.5 - 0.07 * ss(0.07, 0.15, ax) - 0.03 * (1 - ss(0.0, 0.05, ax))
        f_front = np.minimum.reduce([-y - 0.02, 0.148 - ax, z - 1.15, top_f - z])
        top_b = 1.505 - 0.065 * ss(0.07, 0.16, ax)
        f_back = np.minimum.reduce([y - 0.0, 0.158 - ax, z - 1.16, top_b - z])
        f_strap = np.minimum(0.028 - np.abs(ax - 0.098), z - 1.40)
        f_cumm = np.minimum(z - 1.165, 1.3 - z)
        return np.maximum.reduce([f_front, f_back, f_strap, f_cumm])
    G.cut(o, field)
    G.drop_islands(o, 20)

    def off(P, N):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        o_ = np.full(len(P), 0.014)
        o_ += 0.006 * ((ax < 0.13) & (z > 1.2) & (z < 1.48))
        o_ -= 0.006 * ((z > 1.47) & (ax > 0.06))
        return o_

    def gap(P, N):
        return off(P, N) - 0.006
    G.relax_offset(o, B, off, iters=30, lam=0.55, min_gap_fn=gap)
    G.rim(o, 0.008)
    G.smooth_shading(o)
    G.set_material(o, "Cloth_Gear")
    panel_unwrap(o, [_front_back])
    a = o.data.attributes.new("vest", "FLOAT", "POINT")
    a.data.foreach_set("value", np.ones(len(o.data.vertices), np.float32))
    self.objs["ChestRig"] = o
    B.push_layer(o)
    self.B._outer = None
    return o


def _placard(self):
    B = self.B
    # placard: stiff panel across the lower front with three pouches (centre one with an olive flap), side buckles
    ctx = GearCtx(B)
    pp = gear.Part("ChestRigPlacard")
    hit, hn = surf(ctx, np.array((0.0, 0.0, 1.232)), (0, -1, 0.02), 0.4)
    if hit is not None:
        r_, u_, n_ = gear.frame_from(nrm(hn * 0.3 + np.array((0, -1.0, 0))), (0, 0, 1))
        base = hit + n_ * 0.006
        gear.rbox(pp, base, r_, u_, n_, (0.235, 0.112, 0.012), bevel=0.004, segments=2, mat="Cloth_Gear", attrs={"pouch": 4.0})
        for (dx, w, h, d, fl) in ((-0.074, 0.058, 0.098, 0.03, 2.0), (0.0, 0.074, 0.104, 0.036, 3.0), (0.074, 0.058, 0.098, 0.03, 2.0)):
            c = base + r_ * dx + n_ * 0.006 + u_ * 0.004
            pc = c + n_ * (d * 0.5 + 0.002)
            gear.rbox(pp, pc, r_, u_, n_, (w, h, d), bevel=min(0.008, d * 0.35), segments=2, mat="Cloth_Gear", attrs={"pouch": 1.0})
            fc = pc + u_ * (h * 0.3) + n_ * (d * 0.5 + 0.0026)
            gear.rbox(pp, fc, r_, u_, n_, (w * 1.05, h * 0.44, 0.0065), bevel=0.0026, segments=1, mat="Cloth_Gear", attrs={"pouch": fl})
            gear.rbox(pp, fc - u_ * (h * 0.21) + n_ * 0.0032, r_, u_, n_, (w * 1.03, 0.013, 0.0055), bevel=0.0018, segments=1,
                      mat="Cloth_Gear", attrs={"pouch": fl})
            if fl == 2.0:
                # vertical retention strap with a ladder-lock buckle
                s0 = fc + u_ * 0.012 + n_ * 0.0045
                s1 = pc - u_ * (h * 0.18) + n_ * (d * 0.5 + 0.0012)
                P_ = np.array([s0 + (s1 - s0) * k / 7 for k in range(8)])
                N_ = np.tile(n_, (8, 1))
                gear.strap(pp, P_, N_, 0.016, 0.0022, mat="Cloth_Gear", attrs={"strap": 1.0})
                # black moulded strap keeper (concept: no bright hardware on the pouches)
                gear.rbox(pp, s0 + (s1 - s0) * 0.62 + n_ * 0.0042, r_, u_, n_, (0.021, 0.013, 0.004), bevel=0.0014, segments=1,
                          mat="Cloth_Gear", attrs={"strap": 1.0})
            else:
                gear.bolt(pp, fc - u_ * (h * 0.15) + n_ * 0.0036, n_, u_, 0.0058, 0.0024, 0.0, sides=12, mat="Cloth_Gear")
    # cummerbund side straps (elastic + webbing tabs) visible under the jacket hem line
    for sd in (1, -1):
        hit, hn = surf(ctx, np.array((sd * 0.12, 0.0, 1.21)), nrm(np.array((sd * 1.0, -0.6, 0.0))), 0.4)
        if hit is None:
            continue
        r_, u_, n_ = gear.frame_from(hn, (0, 0, 1))
        for dz in (-0.022, 0.022):
            gear.rbox(pp, hit + u_ * dz + n_ * 0.003, r_, u_, n_, (0.06, 0.02, 0.004), bevel=0.0015, segments=1, mat="Cloth_Gear",
                      attrs={"strap": 1.0})
    po = pp.build()
    self.objs["ChestRig"] = gear.join([self.objs["ChestRig"], po], "ChestRig")
    self.B._outer = None



def chest_plate(self):
    """Concept chest plate: a wide contoured satin-black plate filling the open front of the jacket (sternum notch under
    the turtleneck, shoulders of the plate rising towards the carrier straps), a raised yoke piece under the collar and a
    raised horizontal band with chamfered ends across the middle; recessed panel line inside the border."""
    B = self.B
    ctx = GearCtx(B)
    part = gear.Part("ChestPlate")
    piv = np.array((0.0, 0.13, 1.40))
    hit, hn = surf(ctx, np.array((0.0, 0.0, 1.41)), (0, -1, 0.05), 0.5)
    poly = [(-1, 0.7), (-0.76, 0.95), (-0.46, 1.0), (-0.24, 0.9), (0.24, 0.9), (0.46, 1.0), (0.76, 0.95), (1, 0.7),
            (1, -0.76), (0.86, -1), (-0.86, -1), (-1, -0.76)]
    gear.plate(ctx, part, hit, nrm(hn * 0.2 + np.array((0, -1.0, 0.0))), (0, 0, 1), 0.13, 0.116, offset=0.004, thickness=0.011,
               crown=0.012, chamfer=0.004, poly=poly, corner=0.07, groove=0.86, groove_depth=0.0014, segs=72, plate_id=10, zone=3,
               edge_zone=3, mode="radial", pivot=piv, cast_r=0.45, clearance=0.003,
               bolts=[(-0.86, 0.5), (0.86, 0.5), (-0.8, -0.82), (0.8, -0.82)])
    o = part.build()
    B.push_layer(o)
    p2 = gear.Part("ChestPlate2")
    # yoke under the collar (trapezoid, lower corners chamfered) and the mid band (long hexagon)
    for (zc, w, h, poly2, pid) in ((1.482, 0.082, 0.028, [(-1, 1), (1, 1), (1, -0.2), (0.72, -1), (-0.72, -1), (-1, -0.2)], 11),
                                   (1.395, 0.11, 0.0125, [(-0.86, 1), (0.86, 1), (1, 0), (0.86, -1), (-0.86, -1), (-1, 0)], 12)):
        hit, hn = surf(ctx, np.array((0.0, 0.0, zc)), (0, -1, 0.05), 0.5)
        if hit is None:
            continue
        gear.plate(ctx, p2, hit, nrm(hn * 0.3 + np.array((0, -1.0, 0))), (0, 0, 1), w, h, offset=0.0006, thickness=0.0035, crown=0.002,
                   chamfer=0.0018, poly=poly2, corner=0.12, segs=40, plate_id=pid, zone=3, edge_zone=3, clearance=0.001,
                   mode="radial", pivot=piv, cast_r=0.4)
    o2 = p2.build()
    B.layers = [l for l in B.layers if l is not o]
    o = gear.join([o, o2], "ChestPlate")
    B.push_layer(o)
    self.objs["ChestPlate"] = o
    B._outer = None
    if "ChestRig" in self.objs:
        _placard(self)
    return o


Outfit.chest_rig = chest_rig
Outfit.chest_plate = chest_plate


# ============================================================================= cargo trousers


def straighten_legs(o, L, z0=0.42, z1=0.97, hang=0.986, low_blend=0.0):
    """Cargo trousers hang: per leg, the cross-section centre follows a straight line and the radius hangs down from
    the widest point above (slow taper), so the offset shell stops tracing the knee and calf like leggings."""
    co = K.get_co(o)
    out = co.copy()
    for side in (1, -1):
        m = (np.sign(co[:, 0]) == side) & (co[:, 2] > z0 - 0.02) & (co[:, 2] < z1 + 0.02)
        if m.sum() < 50:
            continue
        P = co[m]
        bins = np.arange(z0, z1 + 0.0101, 0.01)
        cx, cy, rr, zz = [], [], [], []
        for b0 in bins:
            q = P[(P[:, 2] >= b0) & (P[:, 2] < b0 + 0.01)]
            if len(q) < 6:
                continue
            c = q[:, :2].mean(0)
            r = np.percentile(np.linalg.norm(q[:, :2] - c, axis=1), 80)
            cx.append(c[0]); cy.append(c[1]); rr.append(r); zz.append(b0 + 0.005)
        zz = np.array(zz); cx = np.array(cx); cy = np.array(cy); rr = np.array(rr)
        sel = (zz > 0.3) & (zz < 0.82)
        ax_ = np.polyfit(zz[sel], cx[sel], 1); ay_ = np.polyfit(zz[sel], cy[sel], 1)
        # hang the radius from the top: never narrower than 98.6 % per cm of the slice above
        rh = rr.copy()
        for i in range(len(rh) - 2, -1, -1):
            rh[i] = max(rr[i], rh[i + 1] * hang)
        zv = P[:, 2]
        cxl = np.polyval(ax_, zv); cyl = np.polyval(ay_, zv)
        cxa = np.interp(zv, zz, cx); cya = np.interp(zv, zz, cy)
        w = 1 - ss(0.84, 0.97, zv)                                   # blend back to the real shape at the seat/hips
        if low_blend > 0:
            w = w * ss(z0, z0 + low_blend, zv)                       # and to the (tapered) shape below z0
        cxn = cxl * w + cxa * (1 - w); cyn = cyl * w + cya * (1 - w)
        d = P[:, :2] - np.stack([cxa, cya], 1)
        r0 = np.linalg.norm(d, axis=1)
        u = d / np.maximum(r0[:, None], 1e-6)
        rt = np.interp(zv, zz, rh)
        rn = np.maximum(r0, rt * (0.86 + 0.14 * np.abs(u[:, 0])))        # slightly oval (narrower front-back)
        rn = r0 * (1 - w) + rn * w
        Pn = P.copy()
        Pn[:, 0] = cxn + u[:, 0] * rn
        Pn[:, 1] = cyn + u[:, 1] * rn
        out[m] = Pn
    K.set_co(o, out)


def pants(self):
    B, L = self.B, self.L
    leg_b = ["Hips", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftButtock", "RightButtock", "Spine"]

    def pred(C, W):
        return (B.wsum(W, leg_b) > 0.5) & (C[:, 2] < 1.16) & (C[:, 2] > 0.2) & (B.wsum(W, ["LeftFoot", "RightFoot"]) < 0.3)
    o = G.shell_from_faces(B, select_faces(B, pred), "Pants")
    G.cut(o, lambda P: 1.158 - 0.012 * ss(-0.04, 0.06, P[:, 1]) - P[:, 2])          # high-rise (olive shows under the carrier)
    # concept: full-length cargo trousers bloused into the tall boots - the leg tapers below the knee and continues
    # INSIDE the boot shaft (slimmer than the shaft, which is built against the body only, so it never flares)
    G.cut(o, lambda P: P[:, 2] - TROUSER_END)
    G.drop_islands(o)

    def off(P, N):
        z = P[:, 2]
        o_ = np.full(len(P), 0.0095)
        o_ += 0.0045 * ss(0.6, 0.74, z) * (1 - ss(0.95, 1.05, z))     # thigh ease (cargo cut)
        o_ += 0.004 * ss(0.0, 0.06, P[:, 1]) * ss(0.62, 0.8, z) * (1 - ss(0.92, 1.0, z))   # seat/back thigh room
        # tapered below the knee into the boot: snug inside the shaft (< the shaft's 15 mm), a little bunching
        # (blousing) just above the boot top
        o_ = np.where(z < 0.6, o_ * ss(0.5, 0.6, z) + TROUSER_IN_BOOT * (1 - ss(0.5, 0.6, z)), o_)
        return o_
    G.relax_offset(o, B, off, iters=40, lam=0.6)
    straighten_legs(o, L, z0=0.6, z1=0.95, hang=0.99, low_blend=0.06)
    G.relax_offset(o, B, lambda P, N: np.where(P[:, 2] < 0.56, TROUSER_IN_BOOT, 0.006), iters=6, lam=0.35)   # clear of the body
    G.rim(o, 0.005)
    G.smooth_shading(o)
    G.set_material(o, "Garment_Pants")
    panel_unwrap(o, [_front_back, lambda P: np.where(P[:, 2] < 0.98, P[:, 0], 1.0)])
    B.push_layer(o)
    # bellows cargo pockets with flaps on both outer thighs, and a slim tool pocket on the right shin side
    ctx = GearCtx(B)
    pp = gear.Part("PantsPockets")
    for side, S in ((1, "Left"), (-1, "Right")):
        hp, kn = L[S + "UpLeg"], L[S + "Leg"]
        c = hp + (kn - hp) * 0.52
        d = nrm(np.array((side * 1.0, -0.5, 0.0)))
        hit, hn = surf(ctx, c, d, 0.3)
        if hit is None:
            continue
        thigh = nrm(hp - kn)
        n_ = nrm(hn * 0.8 + d * 0.2)
        r_, u_, n_ = gear.frame_from(n_, thigh)
        w, h, dd = 0.11, 0.15, 0.013
        pc = hit + n_ * (dd * 0.5 + 0.001)
        gear.rbox(pp, pc, r_, u_, n_, (w, h, dd), bevel=0.007, segments=2, mat="Garment_Pants", attrs={"pouch": 1.0})
        fc = pc + u_ * (h * 0.36) + n_ * (dd * 0.5 + 0.0022)
        gear.rbox(pp, fc, r_, u_, n_, (w * 1.05, h * 0.36, 0.0055), bevel=0.0022, segments=1, mat="Garment_Pants", attrs={"pouch": 2.0})
        gear.rbox(pp, fc - u_ * (h * 0.175) + n_ * 0.0028, r_, u_, n_, (w * 1.03, 0.011, 0.0048), bevel=0.0016, segments=1,
                  mat="Garment_Pants", attrs={"pouch": 2.0})
        for bx in (-0.032, 0.032):
            gear.bolt(pp, fc - u_ * (h * 0.12) + r_ * bx + n_ * 0.0032, n_, u_, 0.0048, 0.002, 0.0, sides=10, mat="Garment_Pants")
    po = pp.build()
    o = gear.join([o, po], "Pants")
    self.objs["Pants"] = o
    B._outer = None
    B.layers[-1] = o
    return o


Outfit.pants = pants


# ============================================================================= knee pads + shin greaves (rigid on the shin bone)


def _surface_path(ctx, pts_ctr, dirs, push=0.0):
    P, N = [], []
    for c, d in zip(pts_ctr, dirs):
        hit, hn = surf(ctx, c, d, 0.2)
        if hit is not None:
            P.append(hit + hn * push); N.append(hn)
    return np.array(P), np.array(N)


def knee_pads(self):
    """Concept knee armour: a black hexagonal knee cap with magenta light bars top and bottom, side bolts, on a padded
    black knee sleeve held by straps above and below the knee. Rigid on the shin bone. (The straight shin plate with
    the cyan/magenta lights belongs to the tall boots.)"""
    B, L = self.B, self.L
    ctx = GearCtx(B)
    for side, S in ((1, "Left"), (-1, "Right")):
        K_ = L[S + "Leg"]
        A_ = L[S + "Foot"]
        H_ = L[S + "UpLeg"]
        shin = nrm(A_ - K_)
        fwd = nrm(np.array((side * 0.06, -1.0, 0.0)) - shin * (np.array((side * 0.06, -1.0, 0.0)) @ shin))
        name = "KneePad" + ("L" if side > 0 else "R")
        p2 = gear.Part(name + "_b")
        # padded knee sleeve: straps around the back of the leg above and below the cap
        thigh = nrm(K_ - H_)
        for (cc, ax) in ((K_ - thigh * 0.085, thigh), (K_ + shin * 0.075, shin)):
            pts, nr = ring_points(ctx, cc, ax, (0, 1, 0), n=22, R=0.1, push=0.002, phi0=math.radians(-105), phi1=math.radians(105),
                                  closed=False)
            gear.strap(p2, pts, nr, 0.022, 0.0035, mat="Cloth_Gear", caps=True, attrs={"strap": 1.0})
        # knee cap: hex plate, magenta bars top and bottom, side bolts
        d = nrm(np.array((side * 0.08, -1.0, 0.08)))
        piv = K_ + np.array((0, 0.025, 0.004))
        up_ = nrm(-shin + np.array((0, 0, 0.3)))
        p3 = gear.Part(name + "_c")
        hit, hn = surf(ctx, piv, d, 0.25)
        if hit is not None:
            gear.plate(ctx, p3, hit, d, up_, 0.072, 0.08, offset=0.007, thickness=0.011, crown=0.018,
                       chamfer=0.0042, poly=[(-0.6, 1), (0.6, 1), (1, 0.4), (1, -0.4), (0.62, -1), (-0.62, -1), (-1, -0.4), (-1, 0.4)],
                       corner=0.1, groove=0.74, groove_depth=0.0015, segs=56, plate_id=40, zone=3, edge_zone=3, mode="radial", pivot=piv,
                       cast_r=0.25, clearance=0.004, bolts=[(-0.82, 0.0), (0.82, 0.0)])
        co3 = p3.build()
        B.push_layer(co3)
        if hit is not None:
            from mathutils.bvhtree import BVHTree
            ctree = BVHTree.FromPolygons([v.co.copy() for v in co3.data.vertices], [list(p.vertices) for p in co3.data.polygons])
            r_, u_, n_ = gear.frame_from(d, up_)
            for yy, ww in ((0.062, 0.038), (-0.06, 0.04)):
                pts = [hit + u_ * yy + r_ * (xx * ww) for xx in np.linspace(-1, 1, 7)]
                P_, N_ = [], []
                for p in pts:
                    h2, n2 = ctx.cast(p + d * 0.1, -d, 0.15, ctree)
                    if h2 is not None:
                        P_.append(h2 + n2 * 0.0004); N_.append(n2)
                if len(P_) > 3:
                    gear.light_strip(p2, np.array(P_), np.array(N_), width=0.0062, height=0.0016, mat="Glow2")
        B.layers = [l for l in B.layers if l is not co3]
        o = gear.join([co3, p2.build()], name)
        self.objs[name] = o
        B._outer = None
    return True


Outfit.knee_pads = knee_pads


# ============================================================================= tall boots with a straight shin plate


def _foot_outline(pts, n=72, welt=0.004):
    """Foot-shaped sole outline around the given points (plan view): per direction from the centroid the outermost
    point, light smoothing, then a welt; heel narrower than the ball of the foot like a real last."""
    P = np.asarray(pts)[:, :2]
    c = np.array((P[:, 0].mean(), (P[:, 1].min() + P[:, 1].max()) * 0.5))
    q = P - c
    ang = np.arctan2(q[:, 0], -q[:, 1])
    rad = np.linalg.norm(q, axis=1)
    rr = np.full(n, np.nan)
    for k in range(n):
        phi = -math.pi + 2 * math.pi * (k + 0.5) / n
        dphi = np.abs((ang - phi + math.pi) % (2 * math.pi) - math.pi)
        sel = dphi < (2 * math.pi / n) * 1.2
        if sel.any():
            rr[k] = rad[sel].max()
    ok = ~np.isnan(rr)
    idx = np.arange(n)
    rr = np.interp(idx, idx[ok], rr[ok], period=n)
    for _ in range(2):
        rr = np.maximum(rr, rr * 0.5 + (np.roll(rr, 1) + np.roll(rr, -1)) * 0.25)
    out = []
    for k in range(n):
        phi = -math.pi + 2 * math.pi * (k + 0.5) / n
        dvec = np.array((math.sin(phi), -math.cos(phi)))
        out.append(c + dvec * (rr[k] + welt))
    return np.array(out), c


def _sole4(part, outline, c):
    """Chunky lug sole under the outline: welt lip, straight sidewall with a lug band, rounded toe spring, heel block
    (about 3.4 cm under the ball, 4.2 cm under the heel). No platform: the sole hugs the upper's footprint."""
    n = len(outline)
    ymin, ymax = outline[:, 1].min(), outline[:, 1].max()
    verts, faces, uvs = [], [], []
    rings = [(-0.004, 0.0), (0.0, -0.08), (0.0015, -0.3), (0.0015, -0.55), (0.003, -0.6), (0.003, -0.86), (0.0, -0.95), (-0.005, -1.0)]
    for k, (ox, oy) in enumerate(outline):
        heel = ss(ymax - 0.11, ymax - 0.06, oy)
        spring = 0.007 * ss(ymin + 0.06, ymin, oy)
        bump = 0.014 * ss(ymin + 0.06, ymin + 0.015, oy)             # rubber toe bumper wrapping up the toe
        top = 0.034 + 0.008 * heel + spring * 0.5 + bump
        bottom = spring
        dv = np.array((ox - c[0], oy - c[1]))
        dv = dv / max(np.linalg.norm(dv), 1e-6)
        lug = 0.0025 * (k % 2)
        for r_, (out_, fz) in enumerate(rings):
            o_ = out_ + (lug if 4 <= r_ <= 5 else 0.0)
            verts.append((ox + dv[0] * o_, oy + dv[1] * o_, top + fz * (top - bottom)))
    R_ = len(rings)
    for k in range(n):
        k2 = (k + 1) % n
        for r in range(R_ - 1):
            a, b = k * R_ + r, k2 * R_ + r
            faces.append([a, a + 1, b + 1, b])
            uvs.append([(k / n * 2, 1 - r / R_ * 0.3), (k / n * 2, 1 - (r + 1) / R_ * 0.3), ((k + 1) / n * 2, 1 - (r + 1) / R_ * 0.3),
                        ((k + 1) / n * 2, 1 - r / R_ * 0.3)])
    cc = len(verts); verts.append((c[0], c[1], 0.0))
    for k in range(n):
        a_ = k * R_ + R_ - 1; b_ = ((k + 1) % n) * R_ + R_ - 1
        faces.append([a_, cc, b_])
        uvs.append([((verts[a_][0] - c[0]) * 4 + 0.5, (verts[a_][1] - c[1]) * 4 + 0.5), (0.5, 0.5),
                    ((verts[b_][0] - c[0]) * 4 + 0.5, (verts[b_][1] - c[1]) * 4 + 0.5)])
    # insole: closes the top so nothing of the foot shows between the upper and the welt
    ct = len(verts); verts.append((c[0], c[1], 0.03))
    for k in range(n):
        a_ = k * R_; b_ = ((k + 1) % n) * R_
        faces.append([b_, ct, a_])
        uvs.append([(0.9, 0.9), (0.95, 0.95), (0.9, 0.95)])
    part.add(np.array(verts), faces, "Boots", uvs, {"sole": 1.0})


def boots(self):
    B, L = self.B, self.L
    ctx = GearCtx(B)
    foot_b = ["LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase", "LeftLeg", "RightLeg"]

    def pred(C, W):
        return (B.wsum(W, foot_b) > 0.5) & (C[:, 2] < 0.56)
    o = G.shell_from_faces(B, select_faces(B, pred), "Boots")
    an_y = L["LeftFoot"][1]
    G.cut(o, lambda P: BOOT_TOP_F + (BOOT_TOP_B - BOOT_TOP_F) * ss(-0.03, 0.05, P[:, 1] - an_y) - P[:, 2])
    G.cut(o, lambda P: P[:, 2] - 0.02)
    G.drop_islands(o, 20)

    def off(P, N):
        z = P[:, 2]
        toe = ss(0.0, -0.09, P[:, 1] - an_y)
        o_ = np.full(len(P), 0.0075)
        o_ += 0.0075 * ss(0.12, 0.2, z)                                  # shaft over the tucked trousers (straight, no flare)
        o_ += 0.002 * ss(0.14, 0.06, z)                                  # padded collar of the lower boot
        o_ += 0.005 * toe * ss(0.12, 0.05, z)                            # toe box
        o_ += 0.003 * ss(0.075, 0.035, z)                                # meets the sole welt
        return o_
    # against the body only: the tucked trousers stay inside, the shaft follows the leg (no flare)
    G.relax_offset(o, B, off, iters=34, lam=0.6, tree=B.tree)
    # the upper stands on the sole: nothing below the sole top
    co_ = K.get_co(o)
    co_[:, 2] = np.maximum(co_[:, 2], 0.024)
    K.set_co(o, co_)
    G.drop_degenerate(o)
    G.rim(o, 0.006)
    G.smooth_shading(o)
    G.set_material(o, "Boots")
    G.unwrap(o)
    B.push_layer(o)
    co = K.get_co(o)
    E, bE, isb = G.boundary_info(o)
    part = gear.Part("BootsDetail")
    for side, S in ((1, "Left"), (-1, "Right")):
        an = L[S + "Foot"]; toe = L[S + "ToeBase"]; kn = L[S + "Leg"]
        shin = nrm(an - kn)
        fwd = nrm(np.array((side * 0.04, -1.0, 0.0)) - shin * (np.array((side * 0.04, -1.0, 0.0)) @ shin))
        lat = nrm(np.cross(shin, fwd)) * (1 if side > 0 else -1)
        if (lat @ np.array((side, 0, 0))) < 0:
            lat = -lat
        sel = isb & (np.sign(co[:, 0]) == side) & (co[:, 2] < 0.06)
        if sel.sum() < 6:
            continue
        fb = B.co[(B.co[:, 2] < 0.05) & (np.abs(B.co[:, 0] - an[0]) < 0.09) & (np.sign(B.co[:, 0]) == side)]
        outline, c = _foot_outline(np.vstack([co[sel], fb]), welt=0.004)
        _sole4(part, outline, c)
        # ---- straight shin plate on the shaft (planar fit: follows the leg, no flare), with the concept's lights
        cs = kn + (an - kn) * 0.43
        hit, hn = surf(ctx, cs, fwd, 0.25)
        if hit is not None:
            gp = gear.plate(ctx, part, hit, fwd, -shin, 0.047, 0.15, offset=0.0025, thickness=0.008, crown=0.008, chamfer=0.0034,
                            poly=[(-0.92, 1), (0.92, 1), (1, 0.62), (0.86, -0.45), (0.62, -1), (-0.62, -1), (-0.86, -0.45), (-1, 0.62)],
                            corner=0.12, segs=60, plate_id=42, zone=3, edge_zone=3, mode="planar", cast_r=0.2, clearance=0.002,
                            groove=0.84, groove_depth=0.0013, mat_top="Boots", mat_edge="Boots", mat_wall="Boots", attrs={"plate": 1.0},
                            bolts=[(-0.78, 0.8), (0.78, 0.8), (-0.6, -0.8), (0.6, -0.8)])
            o_, u_, r_ = gp["o"], gp["u"], gp["r"]
            Pf = gp["P"]
            top = gp["top"][0]

            def on_plate(x, y):
                s_ = min(max(abs(x) / gp["a"], abs(y) / gp["b"]), 1.0)
                p, dn = Pf(x, y, gp["crown"] * (1 - s_ * s_) + 0.0003)
                return p, dn
            # cyan bracket light just below the knee cap: straight bar with ends turning up
            pts, nrs = [], []
            for xx in np.linspace(-1, 1, 15):
                yy = 0.118 + 0.02 * ss(0.62, 0.95, abs(xx))
                p, dn = on_plate(xx * 0.036 * (1 if r_ @ lat > 0 else -1), yy)
                pts.append(p); nrs.append(dn)
            gear.light_strip(part, np.array(pts), np.array(nrs), width=0.0058, height=0.0018, mat="Glow")
            # magenta diagonal on the inner front of the plate
            pts, nrs = [], []
            sgn_in = -1 if r_ @ lat > 0 else 1
            for f in np.linspace(0, 1, 7):
                p, dn = on_plate(sgn_in * (0.012 + 0.022 * f), 0.05 - 0.045 * f)
                pts.append(p); nrs.append(dn)
            gear.light_strip(part, np.array(pts), np.array(nrs), width=0.005, height=0.0016, mat="Glow2")
        # magenta strip on the outer side of the shaft (vertical, upper shin)
        pts = [kn + (an - kn) * t + lat * 0.05 for t in np.linspace(0.24, 0.38, 7)]
        P_, N_ = _surface_path(ctx, pts, [nrm(lat * 0.9 + fwd * 0.3)] * 7, push=0.0006)
        if len(P_) > 3:
            gear.light_strip(part, P_, N_, width=0.0048, height=0.0016, mat="Glow2")
        # vent ribs on the inner lower shaft
        for k in range(4):
            t = 0.6 + k * 0.04
            hh, hn2 = surf(ctx, kn + (an - kn) * t, nrm(-lat * 0.8 + fwd * 0.6), 0.25)
            if hh is not None:
                r2, u2, n2 = gear.frame_from(hn2, -shin)
                gear.rbox(part, hh + n2 * 0.0012, r2, u2, n2, (0.026, 0.0042, 0.003), bevel=0.0012, segments=1, mat="Boots",
                          attrs={"plate": 1.0, "cap": 1.0})
        # lacing: two eyelet rows up the tongue with crossing laces (lower boot, below the shin plate)
        t0, t1 = 0.075, 0.16
        rows = []
        for k in range(5):
            z = t0 + (t1 - t0) * k / 4
            yc = an[1] - 0.08 + 0.05 * ss(t0, 0.15, z)
            pr = []
            for sx in (-1, 1):
                p0 = np.array((an[0] + sx * 0.019, yc, z))
                hit, hn = surf(ctx, p0, nrm(np.array((sx * 0.25, -1.0, 0.25 * (1 - ss(t0, 0.15, z))))), 0.15)
                if hit is None:
                    pr = None
                    break
                pr.append((hit, hn))
            if pr:
                rows.append(pr)
        for (a_, an_), (b_, bn_) in rows:
            for (p, n) in ((a_, an_), (b_, bn_)):
                ring = [p + n * 0.0012 + (np.cross(n, (1, 0, 0)) * math.cos(t) + np.cross(n, np.cross(n, (1, 0, 0))) * math.sin(t)) * 0.0032
                        for t in np.linspace(0, 2 * math.pi, 9)]
                gear.tube(part, np.array(ring), 0.0011, 5, mat="Metal")
        for k in range(len(rows) - 1):
            (a0, n0), (b0, m0) = rows[k]
            (a1, n1), (b1, m1) = rows[k + 1]
            for p, q, nn in ((a0, b1, n0), (b0, a1, m0)):
                mid = (p + q) / 2 + nrm(n0 + m0) * 0.004
                gear.tube(part, np.array([p + nn * 0.002, mid, q + nn * 0.002]), 0.0016, 6, mat="Boots", attrs={"strap": 1.0}, caps=True)
        # ankle strap with a buckle (bottom of the shin plate)
        pts, nr = ring_points(ctx, np.array((an[0], an[1] + 0.004, 0.17)), (0, 0, 1), (0, -1, 0), n=32, R=0.15, push=0.0026)
        for _ in range(3):
            pts = pts * 0.5 + (np.roll(pts, 1, 0) + np.roll(pts, -1, 0)) * 0.25
        pts = np.vstack([pts, pts[:1]]); nr = np.vstack([nr, nr[:1]])
        gear.strap(part, pts, nr, 0.024, 0.0034, mat="Boots", attrs={"strap": 1.0})
        i = 6 if side > 0 else 26
        gear.buckle(part, pts[i] + nr[i] * 0.0034, pts[i + 1] - pts[i], nr[i], 0.024, mat="Metal")
        # cyan light strip along the inner midfoot just above the sole (concept)
        ptsf = []
        for t in np.linspace(0.0, 1.0, 9):
            yy = an[1] - 0.02 - 0.1 * t
            hit, hn = surf(ctx, np.array((an[0], yy, 0.05)), np.array((-side * 1.0, 0.1 * t, 0.0)), 0.2)
            if hit is not None:
                ptsf.append((hit + hn * 0.0006, hn))
        if len(ptsf) > 4:
            gear.light_strip(part, np.array([p for p, _ in ptsf]), np.array([n for _, n in ptsf]), width=0.006, height=0.0016, mat="Glow")
    do = part.build()
    decimate_masked(o, 0.7, np.ones(len(o.data.vertices), bool))
    o = gear.join([o, do], "Boots")
    B._outer = None
    self.objs["Boots"] = o
    return o


Outfit.boots = boots


# ============================================================================= pauldrons with hinge brackets


def _shoulder_line(ctx, side):
    """Height of the outer surface (jacket) on top of the shoulder, half way between the neck and the shoulder joint."""
    best = 0.0
    for x in (0.13, 0.15, 0.17, 0.19, 0.21):
        hit, hn = ctx.cast(np.array((side * x, -0.02, 2.2)), np.array((0, 0, -1.0)), 1.0)
        if hit is not None:
            best = max(best, float(hit[2]))
    return best


PAULDRON_MAX_RISE = 0.04      # nothing on the pauldron rises more than 4 cm above the shoulder line (concept)


def _pauldron(self, side, scale=1.0):
    """Concept pauldron: a compact curved brushed-steel plate hugging the top of the deltoid (radially fitted over the
    jacket), one articulated lame below it on the upper arm, a short stacked bracket (three horizontal steel bars in a
    rounded frame) mounted on the plate's upper face, and small cyan / magenta lights. Nothing rises more than
    PAULDRON_MAX_RISE above the shoulder line."""
    B, L = self.B, self.L
    ctx = GearCtx(B)
    S = "Left" if side > 0 else "Right"
    sh = L[S + "Arm"]
    el = L[S + "ForeArm"]
    arm = nrm(el - sh)
    sfx = "L" if side > 0 else "R"
    z_line = _shoulder_line(ctx, side)
    piv = sh + np.array((-side * 0.05, 0.0, -0.035))
    cap = gear.Part("Pauldron" + sfx)
    d = nrm(np.array((side * 0.62, -0.2, 0.76)))
    hit, hn = surf(ctx, piv, d, 0.3)
    up = nrm(np.array((-side * 0.78, 0.0, 0.62)))
    # rounded shield outline: narrower at the top (towards the neck), wide and rounded over the outer deltoid
    poly = [(-0.62, 1.0), (0.62, 1.0), (0.92, 0.55), (1.0, -0.1), (0.86, -0.72), (0.5, -1.0), (-0.5, -1.0), (-0.86, -0.72),
            (-1.0, -0.1), (-0.92, 0.55)]
    gear.plate(ctx, cap, hit, d, up, 0.1 * scale, 0.112 * scale, offset=0.005, thickness=0.016, crown=0.014, chamfer=0.005,
               poly=poly, corner=0.12, groove=0.8, groove_depth=0.0016, segs=60, plate_id=20 + (side > 0), zone=0, edge_zone=2,
               mode="radial", pivot=piv, cast_r=0.3, bolts=[(-0.74, 0.62), (0.74, 0.62), (-0.7, -0.62), (0.7, -0.62)],
               rivets=True, clearance=0.003)
    capo = cap.build()
    B.push_layer(capo)
    from mathutils.bvhtree import BVHTree
    ctree = BVHTree.FromPolygons([capo.matrix_world @ v.co for v in capo.data.vertices], [list(p.vertices) for p in capo.data.polygons])
    br = gear.Part("PauldronBracket" + sfx)
    brf = gear.Part("PauldronBracketFrame" + sfx)
    # ---- stacked bracket on the upper face of the plate, towards the neck (frame across the shoulder, seen from the
    # front as three horizontal bars)
    mount = sh + np.array((-side * 0.035, 0.0, 0.0))
    hit_b, hn_b = ctx.cast(mount + np.array((0, 0, 0.3)), np.array((0, 0, -1.0)), 0.4, ctree)
    if hit_b is not None:
        h_ = nrm(np.array((0, 0, 1.0)) * 0.7 + hn_b * 0.3)
        w_ = nrm(np.array((side * 1.0, 0, 0)) - h_ * (h_[0] * side))
        dp = nrm(np.cross(h_, w_))
        room = PAULDRON_MAX_RISE - (float(hit_b[2]) - z_line) - 0.0075
        H = float(np.clip(room + 0.006, 0.014, 0.03))
        W, D, P_ = 0.06, 0.024, 0.0095
        base = hit_b - h_ * 0.0015
        A_ = {"mz": 0.0, "wear": 1.0, "plate": 24.0}
        gear.rbox(brf, base + h_ * 0.002, w_, dp, h_, (W + 0.012, D + 0.008, 0.006), bevel=0.0022, segments=2, mat="Armor",
                  attrs={"mz": 3.0, "wear": 0.6, "plate": 24.0})
        for cx_ in (-W / 2 + P_ / 2, W / 2 - P_ / 2):
            gear.rbox(brf, base + w_ * cx_ + h_ * (H / 2 + 0.003), w_, dp, h_, (P_, D, H), bevel=0.003, segments=2, mat="Armor", attrs=A_)
        nb = 3
        for k in range(nb):
            hz = 0.003 + H * (k + 0.75) / nb
            gear.rbox(brf, base + h_ * hz, w_, dp, h_, (W - 0.004, D * (0.92 if k == nb - 1 else 0.8), 0.0062), bevel=0.0022,
                      segments=2, mat="Armor", attrs=A_)
        for cx_ in (-W / 2 + P_ + 0.0004, W / 2 - P_ - 0.0004):
            gear.rbox(brf, base + w_ * cx_ + h_ * (H * 0.5 + 0.003) - dp * (D * 0.3), w_, dp, h_, (0.0016, D * 0.25, H * 0.7),
                      bevel=0.0, segments=0, mat="Glow")
        # hard limit: nothing above PAULDRON_MAX_RISE over the shoulder line (sink the bracket into its mount if needed)
        if brf.V:
            zmax = float(np.vstack(brf.V)[:, 2].max())
            excess = zmax - (z_line + PAULDRON_MAX_RISE)
            if excess > 0:
                brf.V = [v - h_[None] * (excess / max(h_[2], 0.3)) for v in brf.V]

    # ---- small lights on the plate: cyan on the upper outer front, magenta bar at the lower outer edge
    for (dd, mat, size) in ((nrm(np.array((side * 0.75, -0.62, 0.35))), "Glow", (0.012, 0.006, 0.0022)),
                            (nrm(np.array((side * 1.0, -0.3, -0.25))), "Glow2", (0.022, 0.0055, 0.0022))):
        hit2, hn2 = ctx.cast(piv + dd * 0.3, -dd, 0.35, ctree)
        if hit2 is not None:
            r_, u_, n_ = gear.frame_from(hn2, (0, 0, 1))
            gear.rbox(br, hit2 + n_ * 0.0006, r_, u_, n_, size, bevel=0.0012, segments=1, mat=mat)
    bro = br.build()
    brfo = brf.build()
    capo = gear.join([capo, bro, brfo], "Pauldron" + sfx)
    B._outer = None
    # ---- one articulated lame on the upper arm under the plate's lower edge, hinged front and back
    lam = gear.Part("PauldronLame" + sfx)
    c = sh + (el - sh) * 0.33
    dd = nrm(np.array((side * 1.0, -0.3, 0.0)) - arm * (np.array((side * 1.0, -0.3, 0.0)) @ arm))
    hit, hn = surf(ctx, c, dd, 0.2)
    if hit is not None:
        gear.plate(ctx, lam, hit, dd, -arm, 0.084 * scale, 0.03 * scale, offset=0.006, thickness=0.01, crown=0.008, chamfer=0.0036,
                   poly=[(-1, 1), (1, 1), (0.9, -1), (-0.9, -1)], corner=0.2, segs=40, plate_id=22, zone=0, edge_zone=2,
                   mode="radial", pivot=c, cast_r=0.2, clearance=0.003, rivets=False, bolts=[(-0.84, 0.0), (0.84, 0.0)])
    lamo = lam.build()
    self.objs[capo.name] = capo
    self.objs[lamo.name] = lamo
    B.push_layer(lamo)
    co = np.vstack([K.get_co(capo), K.get_co(lamo)])
    K.log("PAULDRON", sfx, "shoulder line", round(z_line, 3), "max rise", round(float(co[:, 2].max()) - z_line, 4))
    return capo, lamo


def pauldrons(self):
    _pauldron(self, 1, 1.0)
    _pauldron(self, -1, 1.0)


Outfit.pauldrons = pauldrons


# ============================================================================= gloves: knuckle studs + wrist strap


def _stud(part, p, n, up, radius, height, sides=14, mat="Gloves", attrs=None):
    """Round bevelled stud (cylinder + chamfered top)."""
    n = nrm(n)
    u = nrm(np.asarray(up) - n * (np.asarray(up) @ n))
    r = np.cross(u, n)
    V = []
    rings = ((radius, -0.0008), (radius, height * 0.7), (radius * 0.8, height), (radius * 0.45, height * 1.05))
    for rad, h in rings:
        for k in range(sides):
            t = 2 * math.pi * k / sides
            V.append(p + (r * math.cos(t) + u * math.sin(t)) * rad + n * h)
    V.append(p + n * height * 1.08)
    F = []
    for ring in range(len(rings) - 1):
        for k in range(sides):
            a, b = ring * sides + k, ring * sides + (k + 1) % sides
            F.append([a, b, b + sides, a + sides])
    c = len(V) - 1
    for k in range(sides):
        F.append([(len(rings) - 1) * sides + k, (len(rings) - 1) * sides + (k + 1) % sides, c])
    sharp = [((0 * sides) + k, (0 * sides) + (k + 1) % sides) for k in range(sides)]
    part.add(np.array(V), F, mat, None, attrs, sharp)


def _dome(part, p, n, up, radius, height, sides=18, mat="Cloth_Brass", attrs=None):
    """Polished brass knuckle stud: short cylinder wall + hemispherical dome."""
    n = nrm(n)
    u = nrm(np.asarray(up) - n * (np.asarray(up) @ n))
    r = np.cross(u, n)
    prof = [(1.0, -0.0006)] + [(math.cos(a), 0.25 * height + 0.75 * height * math.sin(a)) for a in np.linspace(0, math.pi / 2 * 0.92, 6)]
    V = []
    for rad_k, h in prof:
        for k in range(sides):
            t = 2 * math.pi * k / sides
            V.append(p + (r * math.cos(t) + u * math.sin(t)) * radius * rad_k + n * h)
    V.append(p + n * height * 1.0)
    F = []
    R = len(prof)
    for ring in range(R - 1):
        for k in range(sides):
            a, b = ring * sides + k, ring * sides + (k + 1) % sides
            F.append([a, b, b + sides, a + sides])
    c = len(V) - 1
    for k in range(sides):
        F.append([(R - 1) * sides + k, (R - 1) * sides + (k + 1) % sides, c])
    part.add(np.array(V), F, mat, None, attrs)


def gloves(self):
    """Concept: bulky black tactical gloves, a padded knuckle guard with FOUR large polished brass studs (dark bezels),
    a back-of-hand plate and a wide wrist cuff."""
    o = O2.gloves(self)
    B, L = self.B, self.L
    sh0 = (_attr(o, "kplate") < 0.5)
    vn = K.vertex_normals_fast(o)
    K.set_co(o, K.get_co(o) + vn * (0.0024 * sh0)[:, None])         # chunkier glove shell (plates kept)
    B._outer = None
    ctx = GearCtx(B)
    part = gear.Part("GloveStuds")
    KA = {"kplate": 1.0, "mz": 2.0}
    for s in (1, -1):
        wr, dors, fdir, mcp = gear.hand_frame(L, s)
        hits = []
        for k, m in enumerate(mcp[:4]):
            dd = nrm(dors * 0.6 + fdir * 0.4)
            hit, hn = surf(ctx, m, dd, 0.1)
            if hit is not None:
                hits.append((hit, nrm(hn * 0.5 + dd * 0.5)))
        if len(hits) >= 2:
            # padded knuckle guard under the studs (black), spanning the four knuckles
            P0 = np.array([h for h, _ in hits]); N0 = np.array([n for _, n in hits])
            c = P0.mean(0); nn = nrm(N0.mean(0))
            across = nrm(P0[-1] - P0[0])
            span = float(np.linalg.norm(P0[-1] - P0[0])) + 0.024
            up_ = nrm(np.cross(nn, across))
            gear.rbox(part, c + nn * 0.004, across, up_, nn, (span, 0.022, 0.008), bevel=0.0035, segments=2, mat="Gloves",
                      attrs={**KA, "cuffplate": 0.0})
            for (h, n_) in hits:
                base = h + n_ * 0.0075
                _dome(part, base - n_ * 0.0005, n_, fdir, 0.0112, 0.0024, sides=18, mat="Gloves", attrs={**KA, "cuffplate": 1.0})  # bezel
                _dome(part, base + n_ * 0.0016, n_, fdir, 0.0092, 0.0068, sides=18, mat="Cloth_Brass", attrs={**KA, "stud": 1.0})
        # wide wrist cuff with a plate tab
        S = "Left" if s > 0 else "Right"
        E, W = L[S + "ForeArm"], L[S + "Hand"]
        ax = nrm(W - E)
        rc = E + (W - E) * 0.92
        pts, nr = ring_points(ctx, rc, ax, dors, n=24, R=0.12, push=0.0016)
        pts = np.vstack([pts, pts[:1]]); nr = np.vstack([nr, nr[:1]])
        gear.strap(part, pts, nr, 0.026, 0.0042, mat="Gloves", attrs={"strap": 1.0, "kplate": 0.0})
        hit, hn = surf(ctx, rc, dors, 0.12)
        if hit is not None:
            r_, u_, n_ = gear.frame_from(hn, ax)
            gear.rbox(part, hit + n_ * 0.0062, r_, u_, n_, (0.034, 0.024, 0.005), bevel=0.0018, segments=1, mat="Gloves",
                      attrs={"kplate": 0.0, "mz": 2.0, "cuffplate": 1.0})
    po = part.build()
    shell = (_attr(o, "kplate") < 0.5)
    decimate_masked(o, 0.6, shell)
    o = gear.join([o, po], "Gloves")
    B._outer = None
    self.objs["Gloves"] = o
    return o


Outfit.gloves = gloves


# ============================================================================= right-forearm interface: rings + circuit traces


def _ring_glow(ctx, part, c, ax, ref, push_metal, push_glow, r_metal=0.0045, r_glow=0.0016, plate=33.0, shift=0.007):
    pts, nr = ring_points(ctx, c, ax, ref, n=30, R=0.15, push=push_metal)
    gear.tube(part, np.vstack([pts, pts[:1]]), r_metal, 10, mat="Armor", attrs={"mz": 2.0, "wear": 0.9, "plate": plate})
    pts2, _ = ring_points(ctx, c + ax * shift, ax, ref, n=30, R=0.15, push=push_glow)
    gear.tube(part, np.vstack([pts2, pts2[:1]]), r_glow, 6, mat="Glow")


def _disc_node(ctx, part, c, d, up, rad=0.011, plate=34.0, push=0.0):
    hit, hn = surf(ctx, c, d, 0.2)
    if hit is None:
        return
    hit = hit + nrm(d) * push
    r_, u_, n_ = gear.frame_from(hn, up)
    ring = [hit + n_ * 0.0035 + (r_ * math.cos(t) + u_ * math.sin(t)) * rad for t in np.linspace(0, 2 * math.pi, 25)]
    gear.tube(part, np.array(ring), 0.0026, 8, mat="Glow")
    ring2 = [hit + n_ * 0.0032 + (r_ * math.cos(t) + u_ * math.sin(t)) * rad * 0.55 for t in np.linspace(0, 2 * math.pi, 17)]
    gear.tube(part, np.array(ring2), 0.0013, 6, mat="Glow")
    gear.rbox(part, hit + n_ * 0.0034, r_, u_, n_, (rad * 0.42, rad * 0.42, 0.0024), bevel=0.0009, segments=1, mat="Glow")


def _holo_panel(ctx, part, E, W, outer, front, t0, t1, a0, a1, push, nt=6, na=5, mat="Glow", wall="Glow", depth=0.0016):
    """Curved light panel on the forearm surface between t0..t1 (along elbow->wrist) and angles a0..a1 (around the
    forearm, 0 = outer side): emissive face plus a brighter border wall down towards the sleeve."""
    grid = []
    for i in range(nt + 1):
        t = t0 + (t1 - t0) * i / nt
        c = E + (W - E) * t
        row = []
        for j in range(na + 1):
            a = a0 + (a1 - a0) * j / na
            d = nrm(outer * math.cos(a) + front * math.sin(a))
            hit, hn = surf(ctx, c, d, 0.15)
            if hit is None:
                hit = c + d * 0.045
            row.append((hit + d * push, d))
        grid.append(row)
    V, F, UV = [], [], []
    for i in range(nt + 1):
        for j in range(na + 1):
            V.append(grid[i][j][0])
    idx = lambda i, j: i * (na + 1) + j
    for i in range(nt):
        for j in range(na):
            F.append([idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j)])
            UV.append([(j / na, i / nt), ((j + 1) / na, i / nt), ((j + 1) / na, (i + 1) / nt), (j / na, (i + 1) / nt)])
    part.add(np.array(V), F, mat, UV)
    # border wall (bright edge) all round
    border = [(i, 0) for i in range(nt + 1)] + [(nt, j) for j in range(1, na + 1)] + [(i, na) for i in range(nt - 1, -1, -1)] + \
             [(0, j) for j in range(na - 1, 0, -1)]
    WV, WF = [], []
    for (i, j) in border:
        p, d = grid[i][j]
        WV += [p, p - d * depth]
    m = len(border)
    for k in range(m):
        k2 = (k + 1) % m
        WF.append([2 * k, 2 * k + 1, 2 * k2 + 1, 2 * k2])
    part.add(np.array(WV), WF, wall, None)


def _arm_frame(L, S, sd, seg):
    """(start, end, axis, outer, front) of the upper arm ('upper') or forearm ('fore') of side S."""
    a, b = (L[S + "Arm"], L[S + "ForeArm"]) if seg == "upper" else (L[S + "ForeArm"], L[S + "Hand"])
    ax = nrm(b - a)
    outer = nrm(np.array((sd, 0.0, 0.0)) - ax * (np.array((sd, 0.0, 0.0)) @ ax))
    front = nrm(np.cross(ax, outer)) * sd
    return a, b, ax, outer, front


def _holo_wrap(ctx, part, a, b, ax, outer, front, t0, t1, push, rng, n_lines=14, n_rings=5, ring_t=None):
    """Holographic wrap made only of saturated light lines (the sleeve shows through - it reads translucent once the
    lines bloom): longitudinal circuit traces with right-angle jogs and end pads, ring segments with gaps, full rings."""
    for k in range(n_lines):
        ang = -math.pi + 2 * math.pi * (k + rng.uniform(0.2, 0.8)) / n_lines
        ta = t0 + (t1 - t0) * rng.uniform(0.0, 0.25); tb = t1 - (t1 - t0) * rng.uniform(0.0, 0.25)
        jt = rng.uniform(0.3, 0.7); jd = rng.choice([-1, 1]) * math.radians(rng.uniform(10, 22))
        pts = []
        for t in np.linspace(ta, tb, 14):
            f = (t - ta) / max(tb - ta, 1e-6)
            a_ = ang + jd * ss(jt - 0.04, jt + 0.04, f)
            d = nrm(outer * math.cos(a_) + front * math.sin(a_))
            hit, hn = surf(ctx, a + (b - a) * t, d, 0.15)
            if hit is not None:
                pts.append((hit + d * push, d))
        if len(pts) > 5:
            P_ = np.array([p for p, _ in pts]); N_ = np.array([n for _, n in pts])
            gear.light_strip(part, P_, N_, width=0.0026 if k % 3 else 0.0038, height=0.0011, mat="Glow")
            for (p, n) in (pts[0], pts[-1]):
                r_, u_, n_ = gear.frame_from(n, ax)
                gear.rbox(part, p + n_ * 0.0007, r_, u_, n_, (0.005, 0.005, 0.0014), bevel=0.0005, segments=1, mat="Glow")
    ts = ring_t if ring_t is not None else np.linspace(t0 + 0.06, t1 - 0.06, n_rings)
    for j, t in enumerate(ts):
        c = a + (b - a) * t
        if j % 2 == 0:
            pts, nr = ring_points(ctx, c, ax, outer, n=36, R=0.15, push=push + 0.0004)
            gear.light_strip(part, np.vstack([pts, pts[:1]]), np.vstack([nr, nr[:1]]), width=0.0032, height=0.0012, mat="Glow")
        else:
            for (p0, p1) in ((-150, -40), (-20, 70), (95, 165)):          # ring segments with gaps
                pts, nr = ring_points(ctx, c, ax, outer, n=10, R=0.15, push=push + 0.0004, phi0=math.radians(p0),
                                      phi1=math.radians(p1), closed=False)
                gear.light_strip(part, pts, nr, width=0.0042, height=0.0012, mat="Glow")


def _holo_panel_frame(ui, pc, r_, u_, n_, w, h, wid=0.0028, inner=True, bars=4, rng=None):
    def frame(w_, h_, wd, x0=0.0, y0=0.0):
        q = [pc + r_ * (x0 + x) + u_ * (y0 + y) for (x, y) in ((-w_ / 2, -h_ / 2), (w_ / 2, -h_ / 2), (w_ / 2, h_ / 2), (-w_ / 2, h_ / 2),
                                                               (-w_ / 2, -h_ / 2))]
        for a_, b_ in zip(q[:-1], q[1:]):
            P_ = np.array([a_ + (b_ - a_) * f for f in np.linspace(0, 1, 4)])
            gear.light_strip(ui, P_, np.tile(n_, (4, 1)), width=wd, height=0.0008, mat="Glow")
    frame(w, h, wid)
    if inner:
        frame(w * 0.8, h * 0.86, wid * 0.55)
    for j in range(bars):
        bw = w * (0.25 + 0.35 * ((j * 37) % 7) / 7.0)
        y = h * 0.3 - j * h * 0.13
        gear.rbox(ui, pc + r_ * (-w * 0.32 + bw / 2) + u_ * y, r_, u_, n_, (bw, 0.003, 0.001), bevel=0.0, segments=0, mat="Glow")
    ring = [pc + u_ * (-h * 0.27) + r_ * (w * 0.2) + (r_ * math.cos(t) + u_ * math.sin(t)) * min(w, h) * 0.13
            for t in np.linspace(0, 2 * math.pi, 19)]
    gear.tube(ui, np.array(ring), 0.0011, 5, mat="Glow")


def _holo_shell(ctx, part, a, b, ax, outer, front, t0, t1, push, n_around=28, n_along=14):
    """Translucent holographic fill (material "Holo": additive, unlit; Kael_Holo.png = pattern RGB + coverage A): a
    closed tube over the sleeve between t0 and t1, u around (one wrap), v along the shell 0..1 (the texture fades the
    ends)."""
    V, F, UV = [], [], []
    for i in range(n_along + 1):
        t = t0 + (t1 - t0) * i / n_along
        c = a + (b - a) * t
        for j in range(n_around):
            ang = 2 * math.pi * j / n_around
            d = nrm(outer * math.cos(ang) + front * math.sin(ang))
            hit, hn = surf(ctx, c, d, 0.15)
            if hit is None:
                hit = c + d * 0.045
            V.append(hit + d * push)
    for i in range(n_along):
        for j in range(n_around):
            j2 = (j + 1) % n_around
            a0, a1 = i * n_around + j, i * n_around + j2
            F.append([a0, a1, a1 + n_around, a0 + n_around])
            u0, u1 = j / n_around, (j + 1) / n_around
            v0, v1 = i / n_along, (i + 1) / n_along
            UV.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
    part.add(np.array(V), F, "Holo", UV, {"holo": 1.0})


def forearm_iface(self):
    """Concept Aether interface on his LEFT arm: a glowing cyan holographic wrap from the wrist up past the elbow to the
    middle of the upper arm - light-line circuit traces, ring segments and full rings (the olive sleeve shows through,
    so it reads translucent under bloom; no opaque panels), a bright emitter ring with a disc node at the elbow, a
    bright cuff ring at the wrist, and floating projected panels beside the forearm and the elbow facing forward."""
    B, L = self.B, self.L
    ctx = GearCtx(B)
    sd = IS
    S = IFACE
    rng = np.random.default_rng(23)
    part = gear.Part("ForearmGuard" + ("L" if sd > 0 else "R"))
    E, W, ax, outer, front = _arm_frame(L, S, sd, "fore")
    _holo_wrap(ctx, part, E, W, ax, outer, front, 0.06, 0.9, 0.0042, rng, n_lines=16, ring_t=[0.18, 0.32, 0.46, 0.6, 0.74])
    # upper arm: from just above the elbow to mid upper arm (weighted to the upper arm in build_deform)
    Sh, El, axu, outu, fru = _arm_frame(L, S, sd, "upper")
    _holo_wrap(ctx, part, Sh, El, axu, outu, fru, 0.5, 0.96, 0.0048, rng, n_lines=12, ring_t=[0.56, 0.68, 0.8])
    # bright rings: elbow emitter (metal + glow) with a disc node, wrist cuff
    _ring_glow(ctx, part, E + (W - E) * 0.04, ax, outer, 0.0066, 0.009, r_metal=0.0055, r_glow=0.0024, shift=0.006)
    _ring_glow(ctx, part, W - (W - E) * 0.07, ax, outer, 0.007, 0.0094, r_metal=0.0062, r_glow=0.003, shift=-0.007)
    _disc_node(ctx, part, Sh + (El - Sh) * 0.86, nrm(outu * 0.8 + fru * 0.6), axu, rad=0.019, push=0.0066)
    _disc_node(ctx, part, E + (W - E) * 0.55, nrm(outer * 0.55 + front * 0.85), ax, rad=0.013, push=0.0062)
    # translucent glowing wrap over the line work (additive "Holo" material): forearm and lower upper arm
    _holo_shell(ctx, part, E, W, ax, outer, front, 0.02, 0.93, 0.0085)
    _holo_shell(ctx, part, Sh, El, axu, outu, fru, 0.46, 1.0, 0.009, n_along=10)
    go = part.build()
    B.push_layer(go)
    self.objs[go.name] = go
    # projected panels beside the outer forearm and the elbow, facing forward in the arms-down stance
    ui = gear.Part("Interface")
    for (seg, t, w, h, off) in (("fore", 0.5, 0.072, 0.11, 0.064), ("fore", 0.12, 0.05, 0.07, 0.07)):
        a, b, ax_, ou, fr = (E, W, ax, outer, front)
        c = a + (b - a) * t
        hit, hn = surf(ctx, c, ou, 0.2)
        if hit is None:
            continue
        n_ = nrm(fr * 0.92 + ou * 0.38)
        u_ = nrm(-ax_ - n_ * (-ax_ @ n_))
        r_ = np.cross(u_, n_)
        if r_ @ ou < 0:
            r_ = -r_
        pc = hit + ou * off + n_ * 0.006
        _holo_panel_frame(ui, pc, r_, u_, n_, w, h, wid=0.003 if w > 0.06 else 0.0024, bars=4 if w > 0.06 else 2)
        stem = np.array([hit + ou * 0.004 + (pc - r_ * (w / 2) - hit - ou * 0.004) * f for f in np.linspace(0, 1, 5)])
        gear.tube(ui, stem, 0.0009, 5, mat="Glow")
    uo = ui.build()
    self.objs["Interface"] = uo
    B._outer = None
    return go, uo


Outfit.forearm_r = forearm_iface


# ============================================================================= belt: plain duty belt with a buckle (no hip pouches, as in the concept)


def belt(self):
    B = self.B
    ctx = GearCtx(B)
    part = gear.Part("Belt")
    rows = []
    for z in (1.0, 1.02, 1.04):
        pts, _ = ring_points(ctx, np.array((0.0, -0.01, z)), (0, 0, 1), (0, -1, 0), n=48, R=0.35, push=0.006)
        rows.append(pts)
    bo = band_mesh("BeltBand", rows, "Cloth_Gear").build()
    sol = bo.modifiers.new("sol", "SOLIDIFY"); sol.thickness = 0.005; sol.offset = 1.0; sol.use_even_offset = True
    gear.apply_modifiers(bo)
    B.push_layer(bo)
    hit, hn = surf(ctx, np.array((0.0, 0.0, 1.02)), (0, -1, 0), 0.4)
    if hit is not None:
        r_, u_, n_ = gear.frame_from(hn, (0, 0, 1))
        # low-profile black polymer buckle (the concept shows no bright hardware at the waist)
        gear.rbox(part, hit + n_ * 0.0075, r_, u_, n_, (0.05, 0.036, 0.007), bevel=0.0024, segments=2, mat="Armor",
                  attrs={"mz": 3.0, "plate": 13.0})
        gear.rbox(part, hit + n_ * 0.0115, r_, u_, n_, (0.032, 0.02, 0.002), bevel=0.0008, segments=1, mat="Armor",
                  attrs={"mz": 3.0, "plate": 13.0})
    po = part.build()
    o = gear.join([bo, po], "Belt")
    B._outer = None
    self.objs["Belt"] = o
    return o


Outfit.belt = belt
