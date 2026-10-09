"""Stage 4: Giva's hard-surface gear and straps (low-poly game meshes + high-poly bake sources).

  blender -b out/giva_suit.blend --python s4_gear.py [-- --only ShoulderR,Harness]
Saves out/giva_gear.blend (game meshes parented to the rig; high-poly sources in collection 'HIGH').
"""
import bpy, sys, os, math, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
import gv, hs, garment
for m in (gv, hs, garment):
    importlib.reload(m)
P = gv.P

A = gv.args()
rig = bpy.data.objects[gv.RIG]
F = garment.Frames(rig)
SUIT = [bpy.data.objects[n] for n in ("Top", "Pants", "Collar") if n in bpy.data.objects]
REF = hs.Ref(SUIT)
HIGH = bpy.data.collections.get("HIGH") or bpy.data.collections.new("HIGH")
if HIGH.name not in bpy.context.scene.collection.children:
    bpy.context.scene.collection.children.link(HIGH)


def finish(part_lo, part_hi, weights_fn):
    lo = part_lo.build()
    gv.link_armature(lo, rig)
    weights_fn(lo)
    if part_hi is not None:
        hi = part_hi.build()
        hi.name = part_lo.name + "_high"
        for c in hi.users_collection:
            c.objects.unlink(hi)
        HIGH.objects.link(hi)
        hi.hide_render = True
    gv.log(part_lo.name, "verts", len(lo.data.vertices), "tris", len(gv.tri_index(lo.data)))
    return lo


# ============================================================================= left pauldron + arm lames
# (mesh keeps the catalog id "ShoulderR": armour sets hide parts by these names)

def shoulder_l(hi):
    p = hs.Part("ShoulderR")
    arm_h, arm_t = F.h["LeftArm"], F.t["LeftArm"]
    ax = gv.nrm(arm_t - arm_h)
    out = gv.nrm(np.array((1.0, 0, 0.55)))
    out = gv.nrm(out - ax * (out @ ax))
    c = arm_h + ax * 0.028 + np.array((-0.014, 0.0, -0.012))
    pole = gv.nrm(out + np.array((-0.2, 0, 0.6)))
    sph = hs.SphChart(REF, c, pole, np.array((0, -1.0, 0)), 0.07)
    # ---- main shell: angular, sweeping forward, dark gunmetal (cls 7)
    shell = hs.rounded_poly([(-0.072, -0.07), (-0.078, 0.06), (0.012, 0.086), (0.062, 0.05), (0.07, -0.02), (0.035, -0.082)],
                            [0.02, 0.026, 0.03, 0.022, 0.024, 0.02])
    EMB = (0.004, -0.004)

    def sh_h(u, v):
        h = 0.0
        r = math.hypot(u - EMB[0], v - EMB[1])
        h -= 0.0028 * gv.ss(0.034, 0.03, r)                       # recessed emblem bay
        if hi:
            h -= 0.0007 * math.exp(-((r - 0.039) / 0.0007) ** 2)  # cut line around the bay
            # panel lines: one front-back over the top, one diagonal at the back
            h -= 0.0006 * math.exp(-((u - 0.045) / 0.0006) ** 2) * (abs(v) < 0.05)
            h -= 0.0006 * math.exp(-(((v - 0.035) + 0.4 * (u + 0.02)) / 0.0006) ** 2) * (u < -0.01)
        return h
    hs.plate(p, sph, shell, gap=0.0065, thick=0.0045, crown=0.007, fillet=0.0022, hi=hi, mat="Armor", height_fn=sh_h,
             cls=7.0)
    # second layer: raised front-top plate (layered armour read)
    top = hs.rounded_poly([(0.018, -0.062), (0.06, -0.03), (0.066, 0.034), (0.03, 0.07), (0.01, 0.05), (0.02, -0.02)],
                          [0.01, 0.014, 0.016, 0.012, 0.012, 0.012])
    hs.plate(p, sph, top, gap=0.0065 + 0.0045 + 0.0045, thick=0.0028, crown=0.006, fillet=0.0014, hi=hi, mat="Armor",
             cls=7.0, lip=False)
    # emblem: glowing ring + dark lens
    gap_s = 0.0065 + 0.0045
    ring = []
    for k in range(48 if hi else 24):
        a_ = 2 * math.pi * k / (48 if hi else 24)
        q, nq = sph.at(EMB[0] + math.cos(a_) * 0.024, EMB[1] + math.sin(a_) * 0.024)
        ring.append(q + nq * (gap_s + 0.0045 + 0.0007))
    ring.append(ring[0])
    hs.tube(p, np.array(ring), 0.0026, "Glow", 4.0, hi, caps=False)
    q, nq = sph.at(*EMB)
    hs.cylinder(p, q + nq * (gap_s + 0.0005), nq, ax, 0.0185, 0.0042, "Armor", 7.0, hi)
    hs.cylinder(p, q + nq * (gap_s + 0.0047), nq, ax, 0.006, 0.0008, "Glow2", 4.0, hi)
    # glowing edge strip along the upper rim of the shell
    pts = []
    for k in range(26):
        t = k / 25
        u_, v_ = 0.055 - 0.012 * t, -0.035 + 0.1 * t
        q, nq = sph.at(u_ - 0.006, v_)
        pts.append(q + nq * (gap_s + 0.0045 + 0.0062 * (1 - (2 * t - 1) ** 2) + 0.0006))
    hs.tube(p, np.array(pts), 0.0018, "Glow", 4.0, hi)
    # bolts
    for (u_, v_) in ((-0.045, -0.045), (-0.05, 0.035), (0.03, -0.05)):
        q, nq = sph.at(u_, v_)
        hs.bolt(p, q + nq * (gap_s + 0.0045 + 0.004), nq, ax, 0.0025, 0.0014, hi)
    global SHOULDER_FLEX_PIDS
    SHOULDER_FLEX_PIDS = p.npieces
    # ---- segmented lames down the upper arm (light, cls 0), overlapping downwards
    front = np.array((0, -1.0, 0))
    front = gv.nrm(front - ax * (front @ ax))
    cyl = hs.CylChart(REF, arm_h, arm_t, gv.nrm(out * 0.55 + front * 0.85), r0=0.055)
    bands = ((0.07, 0.1, 0.09), (0.094, 0.124, 0.088), (0.118, 0.148, 0.085), (0.142, 0.172, 0.082), (0.166, 0.196, 0.078))
    for k, (v0, v1, half) in enumerate(bands):
        poly = hs.rounded_poly([(-half, v0), (half, v0), (half * 0.95, v1), (-half * 0.95, v1)], [0.007, 0.007, 0.01, 0.01])
        gap = 0.005 + 0.003 * k

        def l_h(u, v, v0=v0, v1=v1):
            if not hi:
                return 0.0
            return -0.0005 * math.exp(-((v - (v1 - 0.006)) / 0.0006) ** 2)
        hs.plate(p, cyl, poly, gap=gap, thick=0.0032, crown=0.0016, fillet=0.0014, hi=hi, mat="Armor", height_fn=l_h, cls=0.0)
        for u in (-half * 0.86, half * 0.86):
            q, nq = cyl.at(u, (v0 + v1) / 2)
            hs.bolt(p, q + nq * (gap + 0.0026), nq, ax, 0.002, 0.0011, hi)
    return p


def shoulder_weights(o):
    """Pauldron pieces (everything built before the lames) ride the shoulder surface with one smooth weight field
    (they flex together, no sinking into the deltoid when the arm rises); the lames are rigid per piece."""
    surface_weights(o, rigid=False)
    me = o.data
    pid = np.zeros(len(me.vertices))
    me.attributes["pid"].data.foreach_get("value", pid)
    names, W = gv.bone_weights(o)
    off, idx = gv.neighbours(me)
    X = gv.basis_co(o)
    flex = (pid <= SHOULDER_FLEX_PIDS).astype(float)
    # pauldron: one smooth field (weights of the nearest shell point, averaged over the whole pauldron a little)
    W = gv.smooth(W, off, idx, 25, 0.5, mask=flex)
    sel = flex > 0.5
    Wm = W[sel].mean(0)
    W[sel] = W[sel] * 0.6 + Wm * 0.4
    gv.write_weights(o, names, gv.limit_normalize(W, 4, 0.02))
    rigidify(o, skip=tuple(float(k) for k in range(1, SHOULDER_FLEX_PIDS + 1)))
    o["flex_pids"] = SHOULDER_FLEX_PIDS
    # lames and their rivets: rigid on the upper arm (arm + its counter-twist), the top lame a little on the shoulder
    names, W = gv.bone_weights(o)
    X = gv.basis_co(o)
    a_h, a_t = F.h["LeftArm"], F.t["LeftArm"]
    L = np.linalg.norm(a_t - a_h)
    for k in np.unique(pid):
        if k <= SHOULDER_FLEX_PIDS:
            continue
        sel = pid == k
        t = float(((X[sel].mean(0) - a_h) @ (a_t - a_h)) / L)
        row = {"LeftArm": 0.75, "LeftArmTwist": 0.25} if t > 0.1 else {"LeftArm": 0.8, "LeftArmTwist": 0.1, "LeftShoulder": 0.1}
        for b_, w_ in row.items():
            if P + b_ not in names:
                names.append(P + b_)
                W = np.concatenate([W, np.zeros((len(W), 1))], 1)
        W[sel] = 0
        for b_, w_ in row.items():
            W[sel, names.index(P + b_)] = w_
    gv.write_weights(o, names, gv.limit_normalize(W, 4, 0.02))
    gv.log("ShoulderR (left pauldron): flexible pauldron pids 1..%d, lames rigid" % SHOULDER_FLEX_PIDS)


SHOULDER_FLEX_PIDS = 0


# ============================================================================= helpers

TOR = hs.TorsoChart(REF, F, r0=0.13)


def torso_pt(u, v, push=0.0):
    p, n = TOR.at(u, v)
    return p + n * push, n


def ring_around(z_fn, push, n=96, u_range=None):
    """Closed ring around the torso at height z_fn(phi) (rays from the spine axis)."""
    pts, nor = [], []
    for k in range(n):
        phi = -math.pi + 2 * math.pi * k / n
        p, nn = TOR.at(phi * TOR.r0, z_fn(phi))
        pts.append(p + nn * push)
        nor.append(nn)
    return np.array(pts), np.array(nor)


RIGID_CLS = (0.0, 3.0, 4.0, 6.0, 7.0)      # plates, metal, glow, screen glass: rigid per piece; straps/cables deform


def rigidify(o, skip=()):
    """Every rigid piece (pid) of a gear mesh gets the mean of its vertices' weights (no bending of plates)."""
    me = o.data
    if "pid" not in me.attributes or "cls" not in me.attributes:
        return
    pid = np.zeros(len(me.vertices))
    me.attributes["pid"].data.foreach_get("value", pid)
    fcls = np.zeros(len(me.polygons))
    me.attributes["cls"].data.foreach_get("value", fcls)
    vcls = np.full(len(me.vertices), -1.0)
    for f, c in zip(me.polygons, fcls):
        for v in f.vertices:
            vcls[v] = c
    names, W = gv.bone_weights(o)
    for k in np.unique(pid):
        sel = pid == k
        if k in skip or not np.isin(vcls[sel], RIGID_CLS).all():
            continue
        W[sel] = W[sel].mean(0)
    gv.write_weights(o, names, gv.limit_normalize(W, 3, 0.04))


def surface_weights(o, srcs=None, rigid_bones=None, rigid=True):
    """Deformable gear: weights interpolated from the garments under it (straps, belt, bands)."""
    srcs = srcs or SUIT
    co = gv.basis_co(o)
    best = None
    for s_ in srcs:
        cs = gv.basis_co(s_)
        b = gv.Binding(cs, gv.tri_index(s_.data), co, 0.3)
        names, W = gv.bone_weights(s_)
        w = b.transfer(W)
        if best is None:
            best = (b.D.copy(), {n: w[:, j] for j, n in enumerate(names)})
        else:
            D0, acc = best
            better = b.D < D0
            for j, n in enumerate(names):
                col = acc.get(n, np.zeros(len(co)))
                col[better] = w[better, j]
                acc[n] = col
            for n in list(acc):
                if n not in names:
                    acc[n][better] = 0
            D0[better] = b.D[better]
    names = list(best[1])
    W = np.stack([best[1][n] for n in names], 1)
    gv.write_weights(o, names, gv.limit_normalize(W, 4, 0.01))
    if rigid:
        rigidify(o)


# ============================================================================= Aether harness (core on the upper left chest)

CORE_C = (0.068, 1.372)          # torso chart (u, v) of the core centre (master concept)
CORE_R = 0.058


def cast_in(origin, d):
    """First suit hit from `origin` travelling along d (from outside)."""
    hit, n = REF.cast(origin, d, 1.5)
    return hit, n


def bundle(p, P_, N_, n_cab, r_cab, mats, hi, lift=0.0):
    """Flat bundle of n_cab cables side by side along a surface path (P_, N_)."""
    T = gv.nrm(np.gradient(P_, axis=0))
    B = gv.nrm(np.cross(T, N_))
    out = []
    for k in range(n_cab):
        off = (k - (n_cab - 1) / 2) * r_cab * 2.15
        Q = P_ + N_ * (r_cab + lift) + B * off
        hs.tube(p, Q, r_cab, mats[k % len(mats)][0], mats[k % len(mats)][1], hi, sides=None if hi else 5)
        out.append(Q)
    return out, T, B


def harness(hi):
    p = hs.Part("Harness")
    cu, cv = CORE_C
    up = np.array((0, 0, 1.0))
    # ---------------------------------------------------------------- core housing (dark gunmetal, cls 7)
    outer = hs.superellipse(CORE_R, CORE_R * 0.98, 2.3, 72, c=(cu, cv))

    def base_h(u, v):
        r = math.hypot(u - cu, v - cv)
        h = -0.0085 * gv.ss(0.0445, 0.0405, r)                   # core well
        if hi:
            h -= 0.0007 * math.exp(-((r - 0.051) / 0.0007) ** 2)  # outer cut line
            ang = math.atan2(v - cv, u - cu)
            if -2.6 < ang < -1.2 and 0.045 < r < 0.054:
                h -= 0.001 * (math.cos(ang * 22) > 0.2)          # radial vent slots
        return h
    G_, T_, C_ = 0.004, 0.0085, 0.004
    hs.plate(p, TOR, outer, gap=G_, thick=T_, crown=C_, fillet=0.0028, hi=hi, mat="Armor", height_fn=base_h, cls=7.0)
    c, n = torso_pt(cu, cv)
    top_h = G_ + T_ + C_
    base = c + n * (top_h - 0.0085)
    # recessed reactor: metal bezel, glowing outer ring, dark separator, glowing inner disc, bright centre (each
    # step sits a little lower towards the centre, the lens domes up slightly)
    hs.cylinder(p, base, n, up, 0.0425, 0.0042, "Armor", 7.0, hi, r_top=0.0405)
    hs.cylinder(p, base + n * 0.0005, n, up, 0.039, 0.0049, "Glow", 4.0, hi)
    hs.cylinder(p, base + n * 0.0005, n, up, 0.0285, 0.0055, "Armor", 7.0, hi)
    hs.cylinder(p, base + n * 0.0005, n, up, 0.0235, 0.0060, "Glow", 4.0, hi)
    hs.cylinder(p, base + n * 0.0005, n, up, 0.0125, 0.0068, "Glow2", 4.0, hi, r_top=0.01)
    # bolts round the housing
    for k in range(6):
        a_ = math.radians(30 + 60 * k)
        q, nq = torso_pt(cu + math.cos(a_) * 0.049, cv + math.sin(a_) * 0.049)
        hs.bolt(p, q + nq * (top_h - 0.0012), nq, up, 0.0021, 0.0013, hi)
    # cable sockets: four along the lower-right (her right) rim, three at the bottom
    sock_b, sock_d = [], []
    for k in range(4):
        a_ = math.radians(206 + k * 10.5)
        q, nq = torso_pt(cu + math.cos(a_) * 0.0555, cv + math.sin(a_) * 0.0555)
        hs.cylinder(p, q + nq * 0.004, nq, up, 0.0048, 0.0105, "Metal", 3.0, hi)
        sock_b.append((q, nq))
    for k in range(3):
        a_ = math.radians(254 + k * 12)
        q, nq = torso_pt(cu + math.cos(a_) * 0.0555, cv + math.sin(a_) * 0.0555)
        hs.cylinder(p, q + nq * 0.004, nq, up, 0.0045, 0.0105, "Metal", 3.0, hi)
        sock_d.append((q, nq))
    # ---------------------------------------------------------------- strap over the left shoulder (under the pauldron)
    top_front = torso_pt(cu + 0.01, cv + CORE_R - 0.006)[0]
    shoulder, _ = cast_in(np.array((0.118, -0.012, 1.8)), (0, 0, -1))
    upback, _ = cast_in(np.array((0.095, 0.6, 1.37)), (0, -1, 0))
    conn, _ = cast_in(np.array((0.012, 0.6, 1.285)), (0, -1, 0))
    P_, N_ = hs.surface_path(REF, [top_front, shoulder, upback, conn], 60, push=0.0035)
    hs.strap(p, P_, N_, 0.032, 0.0032, "Cloth_Gear", 1.0, hi)
    # back connector between the shoulder blades
    ch = hs.Chart(REF, np.array((0.006, 0.3, 1.27)), np.array((0, 1.0, 0)), up)
    bk = hs.rounded_poly([(-0.042, 0.036), (0.042, 0.036), (0.048, -0.03), (-0.048, -0.03)], [0.012, 0.012, 0.016, 0.016])

    def bk_h(u, v):
        return -0.0016 * (abs(u) < 0.003 and abs(v) < 0.022) if hi else 0.0
    hs.plate(p, ch, bk, gap=0.0045, thick=0.0085, crown=0.0035, fillet=0.0024, hi=hi, mat="Armor", height_fn=bk_h, cls=7.0)
    q, nq = ch.at(0.0, 0.0)
    hs.rbox(p, q + nq * 0.0132, nq, up, (0.0035, 0.04, 0.002), 0.0008, "Glow2", 4.0, hi)
    # ---------------------------------------------------------------- cable bundle: core -> under the bust -> her
    # right side -> round the back into the connector (4 cables: 3 rubber, 1 glowing)
    s0 = np.mean([q for q, _ in sock_b], 0)
    way = [s0, torso_pt(0.012, 1.215)[0], torso_pt(-0.05, 1.172)[0], torso_pt(-0.115, 1.168)[0], torso_pt(-0.2, 1.18)[0],
           torso_pt(-0.29, 1.205)[0], torso_pt(-0.36, 1.235)[0], torso_pt(-0.41, 1.255)[0]]
    Pb, Nb = hs.surface_path(REF, way, 56 if not hi else 220, push=0.0)
    Pb[0] = s0
    mats = [("Cloth_Gear", 2.0), ("Cloth_Gear", 9.0), ("Glow", 8.0), ("Cloth_Gear", 2.0), ("Cloth_Gear", 9.0)]
    cabs, T, B = bundle(p, Pb, Nb, 5, 0.0029, mats, hi, lift=0.0015)
    # clips holding the bundle (light alloy, her right ribs) + a small one under the bust
    for (uu, vv, big) in ((-0.108, 1.168, True), (-0.03, 1.18, False), (-0.27, 1.2, False)):
        q0, nq = torso_pt(uu, vv)
        i = int(np.argmin(np.linalg.norm(Pb - q0, axis=1)))
        t_ = T[i]
        b_ = np.cross(t_, Nb[i])
        size = (0.036, 0.026 if big else 0.012, 0.0115) if big else (0.032, 0.012, 0.0105)
        hs.rbox(p, Pb[i] + Nb[i] * 0.0058, Nb[i], b_, (size[1], size[0], size[2]), 0.0018, "Armor", 0.0, hi)
        if big:
            hs.rbox(p, Pb[i] + Nb[i] * 0.0118, Nb[i], b_, (0.006, 0.02, 0.0016), 0.0006, "Metal", 3.0, hi)
    # service loop: three cables drop from the core bottom and sweep into the bundle under the bust
    i_m = int(len(Pb) * 0.2)
    for k, (q, nq) in enumerate(sock_d):
        tip = q + nq * 0.0145
        end = cabs[min(k + 1, 4)][i_m] + Nb[i_m] * 0.0062
        mid = (tip + end) / 2 + nq * 0.016 + np.array((0.004 * (k - 1), -0.006, -0.012 - 0.005 * k))
        Pc = hs.catmull(np.array([tip, tip + nq * 0.006 + np.array((0, -0.002, -0.009)), mid, end]), 24 if not hi else 60)
        hs.tube(p, Pc, 0.0026, "Glow" if k == 1 else "Cloth_Gear", 8.0 if k == 1 else (9.0 if k == 2 else 2.0), hi,
                sides=None if hi else 6)
    # ribbed conduit: housing top-left -> pauldron front
    a0, n0 = torso_pt(cu + 0.04, cv + 0.035)
    sh_front = F.h["LeftArm"] + np.array((-0.03, -0.075, 0.035))
    hfront, hn = REF.nearest(sh_front)
    way = [a0 + n0 * 0.012, a0 + n0 * 0.02 + np.array((0.02, 0, 0.02)), hfront + hn * 0.022]
    Pc = hs.catmull(np.array(way), 30 if not hi else 90)
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(Pc, axis=0), axis=1))])
    rad = 0.0062 + (0.0011 * np.sin(L / 0.0045 * 2 * math.pi) if hi else 0.0)
    hs.tube(p, Pc, rad, "Cloth_Gear", 2.0, hi, caps=True)
    # ---------------------------------------------------------------- right shoulder badge + arm glow line
    arm_h, arm_t = F.h["RightArm"], F.t["RightArm"]
    cyl = hs.CylChart(REF, arm_h, arm_t, np.array((-1.0, -0.6, 0.6)), r0=0.05)
    q, nq = cyl.at(0.0, 0.035)
    hs.cylinder(p, q + nq * 0.0015, nq, gv.nrm(arm_t - arm_h), 0.0125, 0.0028, "Armor", 7.0, hi)
    ring = []
    for k in range(33):
        a_ = 2 * math.pi * k / 32
        ring.append(q + nq * 0.0048 + (np.cross(nq, gv.nrm(arm_t - arm_h)) * math.cos(a_) + gv.nrm(arm_t - arm_h) * math.sin(a_)) * 0.0085)
    hs.tube(p, np.array(ring), 0.0012, "Glow", 4.0, hi, caps=False)
    gl = [cyl.at(-0.012, v)[0] + cyl.at(-0.012, v)[1] * 0.0018 for v in np.linspace(0.07, 0.15, 14)]
    hs.tube(p, np.array(gl), 0.0013, "Glow", 4.0, hi)
    return p


def harness_weights(o):
    surface_weights(o)


# ============================================================================= right thigh rig

def thigh_rig(hi):
    p = hs.Part("ThighRig")
    a, b = F.h["RightUpLeg"], F.t["RightUpLeg"]
    ax = gv.nrm(b - a)
    lat = np.array((-1.0, 0.0, 0.0))
    cyl = hs.CylChart(REF, a, b, lat, r0=0.07)
    up = -ax
    # two straps around the thigh
    for v in (0.17, 0.31):
        pts, nor = [], []
        for k in range(96):
            u = (k / 96) * 2 * math.pi * cyl.r0
            q, nq = cyl.at(u, v)
            pts.append(q + nq * 0.0032)
            nor.append(nq)
        hs.strap(p, np.array(pts), np.array(nor), 0.03, 0.003, "Cloth_Gear", 1.0, hi, closed=True)
    # outer plate (rides on the straps) carrying the tool case
    plate_o = hs.rounded_poly([(-0.045, 0.13), (0.045, 0.13), (0.05, 0.35), (-0.04, 0.35)], [0.014, 0.014, 0.018, 0.018])
    plate_o = np.stack([plate_o[:, 0], plate_o[:, 1]], 1)
    hs.plate(p, cyl, plate_o, gap=0.0075, thick=0.005, crown=0.003, fillet=0.002, hi=hi, mat="Armor", cls=7.0)
    # tool case (slim data-spike holster)
    q, nq = cyl.at(0.004, 0.24)
    hs.rbox(p, q + nq * (0.0125 + 0.011), nq, up, (0.042, 0.15, 0.024), 0.006, "Armor", 7.0, hi)
    # sidearm grip out of the holster top (angled back), with a light latch strap over it
    qg, ng = cyl.at(0.004, 0.155)
    gdir = gv.nrm(up * 0.9 + ng * 0.25)
    hs.rbox(p, qg + ng * 0.026 + gdir * 0.03, ng, gdir, (0.03, 0.07, 0.024), 0.006, "Armor", 7.0, hi)
    hs.rbox(p, qg + ng * 0.0255 + gdir * 0.064, ng, gdir, (0.026, 0.012, 0.022), 0.003, "Metal", 3.0, hi)
    q2, nq2 = cyl.at(0.004, 0.19)
    hs.rbox(p, q2 + nq2 * 0.0352, nq2, up, (0.0045, 0.06, 0.0016), 0.0007, "Glow2", 4.0, hi)
    # side-release buckles on both straps (light alloy) and a magnetic latch on the holster
    for v in (0.17, 0.31):
        q, nq = cyl.at(-0.075, v)
        hs.rbox(p, q + nq * 0.0062, nq, ax, (0.034, 0.03, 0.0085), 0.0022, "Armor", 0.0, hi)
        hs.rbox(p, q + nq * 0.0108, nq, ax, (0.02, 0.008, 0.0018), 0.0006, "Metal", 3.0, hi)
    q, nq = cyl.at(0.004, 0.17)
    hs.rbox(p, q + nq * 0.037, nq, up, (0.026, 0.022, 0.006), 0.0018, "Armor", 0.0, hi)
    return p


# ============================================================================= right forearm holo guard
# (mesh keeps the catalog id "ForearmGuardL")

def forearm_guard(hi):
    p = hs.Part("ForearmGuardL")
    a, b = F.h["RightForeArm"], F.t["RightForeArm"]
    ax = gv.nrm(b - a)
    L = float(np.linalg.norm(b - a))
    top = gv.nrm(np.array((-0.3, -0.9, 0.45)))
    cyl = hs.CylChart(REF, a, b, top, r0=0.04)
    v0, v1 = L * 0.38, L * 0.88
    shell = hs.rounded_poly([(-0.066, v0), (0.066, v0 + 0.006), (0.058, v1), (-0.058, v1)], [0.012, 0.012, 0.014, 0.014])
    sc_u, sc_v = 0.0, (v0 + v1) / 2 + 0.004
    SW, SH = 0.05, min(0.085, (v1 - v0) - 0.03)

    def g_h(u, v):
        inside = abs(u - sc_u) < SW / 2 + 0.003 and abs(v - sc_v) < SH / 2 + 0.003
        h = -0.0026 * inside
        if hi:
            d = min(abs(u + 0.052), abs(u - 0.052))
            h -= 0.0006 * math.exp(-(d / 0.0006) ** 2)
        return h
    hs.plate(p, cyl, shell, gap=0.0045, thick=0.0055, crown=0.003, fillet=0.0018, hi=hi, mat="Armor", height_fn=g_h, cls=7.0)
    q, nq = cyl.at(sc_u, sc_v)
    # glowing holo screen (emissive glass) with dark UI lines on it
    # holo screen: glowing magenta glass with dark UI lines, framed by a thin violet light border
    hs.rbox(p, q + nq * 0.0085, nq, ax, (SW, SH, 0.0016), 0.0012, "Glow2", 4.0, hi)
    for (du, dv, w, h_) in ((-0.012, 0.022, 0.02, 0.0024), (0.008, 0.022, 0.012, 0.0024), (0.0, 0.008, 0.036, 0.0018),
                            (0.0, -0.002, 0.03, 0.0018), (-0.008, -0.022, 0.02, 0.008)):
        qq, nn_ = cyl.at(sc_u + du, sc_v + dv)
        hs.rbox(p, qq + nn_ * 0.0096, nn_, ax, (w, h_, 0.0008), 0.0003, "Cloth_Gear", 6.0, hi)
    for (du, dv, w, h_) in ((0.0, SH / 2 + 0.0022, SW + 0.004, 0.0016), (0.0, -SH / 2 - 0.0022, SW + 0.004, 0.0016),
                            (SW / 2 + 0.0022, 0.0, 0.0016, SH), (-SW / 2 - 0.0022, 0.0, 0.0016, SH)):
        qq, nn_ = cyl.at(sc_u + du, sc_v + dv)
        hs.rbox(p, qq + nn_ * 0.0086, nn_, ax, (w, h_, 0.0014), 0.0004, "Glow", 4.0, hi)
    # side buttons and an edge glow strip
    for k in range(3):
        qq, nn_ = cyl.at(0.05, sc_v - 0.02 + k * 0.012)
        hs.cylinder(p, qq + nn_ * 0.0095, nn_, ax, 0.0028, 0.0018, "Metal", 3.0, hi)
    qq, nn_ = cyl.at(-0.05, sc_v)
    hs.rbox(p, qq + nn_ * 0.0095, nn_, ax, (0.003, SH, 0.0015), 0.0006, "Glow2", 4.0, hi)
    # straps under the forearm
    for v in (v0 + 0.012, v1 - 0.012):
        pts, nor = [], []
        for k in range(48):
            u = (0.5 + k / 47) * math.pi * cyl.r0
            qq, nn_ = cyl.at(u + 0.04, v)
            pts.append(qq + nn_ * 0.003)
            nor.append(nn_)
        hs.strap(p, np.array(pts), np.array(nor), 0.016, 0.0028, "Cloth_Gear", 1.0, hi)
    return p


def guard_weights(o):
    gv.rigid_weights(o, [("RightForeArm", 0.55), ("RightForeArmTwist", 0.45)])


# ============================================================================= left leg glow piping (joined into Pants)

def piping(hi):
    import design
    p = hs.Part("Piping")
    pants = bpy.data.objects["Pants"]
    a, b = F.h["LeftUpLeg"], F.t["LeftUpLeg"]
    L1 = float(np.linalg.norm(b - a))
    cyl = hs.CylChart(hs.Ref([pants]), a, b, np.array((1.0, 0, 0)), r0=design.R_LEG)
    # the front edge of the violet outer-thigh panel (design.leg_fields), from the hip to above the knee
    sgn = 1.0 if cyl.at(0.02, 0.2)[0][1] < cyl.at(-0.02, 0.2)[0][1] else -1.0
    pts = []
    for v in np.linspace(0.075, L1 - 0.06, 40 if not hi else 120):
        edge = design.LEG_C - design.leg_half(v, L1)          # lateral edge of the violet thigh panel
        q, nq = cyl.at(sgn * (edge * design.R_LEG - 0.003), v)
        pts.append(q + nq * 0.0021)
    hs.tube(p, np.array(pts), 0.0029, "Glow", 8.0, hi, sides=None if hi else 6)
    return p


def piping_weights(o):
    surface_weights(o, srcs=[bpy.data.objects["Pants"]], rigid=False)


# ============================================================================= HUD visor (left ear unit + holo lens)

def visor(hi):
    """Ear-mounted HUD unit: a sculpted earpiece in front of the left ear and a slim band that hugs the temple to a
    tiny projector at the outer orbital rim (hard-light HUD is projected: nothing covers the eye)."""
    p = hs.Part("Visor")
    body = bpy.data.objects["Body"]
    le = F.h["LeftEye"]
    up = np.array((0, 0, 1.0))
    bref = hs.Ref([body])

    def on_head(q, off):
        h, n = bref.nearest(np.asarray(q, float))
        return h + n * off, n
    # earpiece: rounded capsule over the front of the ear (tragus), slightly above the ear canal
    # a small flush unit just behind the ear root (under the hair; the concept shows no visor)
    ear, ne = on_head(le + np.array((0.052, 0.098, -0.004)), 0.0)
    ch = hs.Chart(bref, ear, ne, up)
    unit = hs.rounded_poly([(-0.0065, 0.009), (0.0065, 0.009), (0.0065, -0.009), (-0.0065, -0.009)], 0.005)
    def u_h(u, v):
        if not hi:
            return 0.0
        return -0.0006 * (abs(math.hypot(u, v - 0.002) - 0.0062) < 0.0006)
    hs.plate(p, ch, unit, gap=0.0015, thick=0.0035, crown=0.0015, fillet=0.0015, hi=hi, mat="Armor", height_fn=u_h, cls=7.0)
    q, nq = ch.at(0.0, 0.0)
    hs.cylinder(p, q + nq * 0.0052, nq, up, 0.0025, 0.0008, "Glow2", 4.0, hi)
    return p


def visor_weights(o):
    gv.rigid_weights(o, [("Head", 1.0)])


PIECES = {"ShoulderR": (shoulder_l, shoulder_weights), "Harness": (harness, harness_weights),
          "ThighRig": (thigh_rig, lambda o: surface_weights(o)), "ForearmGuardL": (forearm_guard, guard_weights),
          "Visor": (visor, visor_weights), "Piping": (piping, piping_weights)}

only = gv.opt(A, "--only")
for name in ("HipModule",):
    if bpy.data.objects.get(name):
        gv.remove(bpy.data.objects[name])
for name, (fn, wf) in PIECES.items():
    if only and name not in only.split(","):
        continue
    old = bpy.data.objects.get(name)
    if old:
        gv.remove(old)
    finish(fn(False), fn(True) if "--nohigh" not in A and name != "Piping" else None, wf)
gv.save(os.path.join(gv.OUT, "giva_gear.blend"))
