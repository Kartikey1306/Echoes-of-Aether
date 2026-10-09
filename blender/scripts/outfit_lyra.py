"""Giva (asset id `lyra`): cyberpunk netrunner / phase engineer outfit (HD pipeline).

Tight bodysuit with glowing circuit traces (scoop neckline showing the collarbones), cropped bomber jacket with a
stand collar and sleeves rolled above the elbow (forearms bare for the tattoos), harness with chest unit, glowing
core and data cables, left hip module, right thigh rig, techwear leggings, robust boots, fingerless gloves, a holo
bracer on the left forearm, a light right shoulder plate, an optional HUD monocle visor and a cyber-eye ring.
Contract meshes: Top, Pants, Gloves, Boots, Harness, ChestUnit, ChestCore, HipModule, ShoulderR, ForearmGuardL,
ConduitL, ConduitR; new optional meshes: Jacket (Garment_Top), ThighRig, Visor, Cyberware.
"""
import math
import numpy as np
import gear
from gear import Part, nrm, ss, shell, plate, pouch, buckle, strap, surface_path, light_strip, tube, rbox, bolt, ring_folds, limb_coords, fbm
from outfit_kael import limb_ring, sole, boot_armor

NAME = "Lyra"


def circuit_paths(rng, start, heading, n, step=(0.01, 0.025), turn=0.5):
    pts = [np.array(start, float)]
    hd = heading
    for _ in range(n):
        if rng.random() < turn:
            hd += rng.choice([-1, 1]) * math.pi / 4
            hd = max(min(hd, heading + math.pi / 2), heading - math.pi / 2)
        pts.append(pts[-1] + np.array((math.cos(hd), math.sin(hd))) * rng.uniform(*step))
    return pts


def build(ctx):
    L, R, B = ctx.L, ctx.region, ctx.B
    co, vn = ctx.basis, ctx.vn
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    rng = np.random.default_rng(21)
    objs = {}
    hips_z = L["Hips"][2]
    sh_L, sh_R = L["LeftArm"], L["RightArm"]
    el_L, el_R = L["LeftForeArm"], L["RightForeArm"]
    wr_L, wr_R = L["LeftHand"], L["RightHand"]
    kn_L, kn_R = L["LeftLeg"], L["RightLeg"]
    an_L, an_R = L["LeftFoot"], L["RightFoot"]
    clav_z = L["LeftShoulder"][2]
    cy = L["Spine1"][1]

    # ------------------------------------------------------------------ bodysuit top (scoop neckline, short sleeves)
    tL, _, _ = limb_coords(co, sh_L, el_L)
    tR, _, _ = limb_coords(co, sh_R, el_R)
    ua = np.linalg.norm(el_L - sh_L)
    neckline = clav_z - 0.045 - 0.02 * ss(0.0, 0.08, np.abs(x)) * 0 + 0.06 * ss(cy - 0.02, cy + 0.06, y)
    top_m = (R["torso"] + R["uarmL"] + R["uarmR"] + R["hips"] * (z > L["Spine"][2])) > 0.5
    top_m &= (R["neck"] < 0.4) & (R["head"] < 0.02) & (R["handL"] < 0.2) & (R["handR"] < 0.2)
    top_m &= z < neckline
    top_m &= ~((x > 0.2) & (tL > ua * 0.8)) & ~((x < -0.2) & (tR > ua * 0.8))
    top_m &= z > L["Spine"][2] - 0.01
    suit = shell(ctx, "Lyra_Top", top_m, lambda P, N: np.full(len(P), 0.0028), mats=("Garment_Top",), smooth=3, subdiv=0, rim=0.003,
                 refine_fn=lambda P: (P[:, 2] > hips_z) & (P[:, 2] < 1.3) & (np.abs(P[:, 0]) < 0.2), refine_iter=1)
    objs["Top"] = suit

    # ------------------------------------------------------------------ leggings (Pants)
    boot_top = an_L[2] + 0.27
    pants_m = ((R["hips"] + R["thighL"] + R["thighR"] + R["shinL"] + R["shinR"] + R["torso"] * (z < L["Spine"][2] + 0.02)) > 0.5)
    pants_m &= (z < L["Spine"][2] + 0.02) & (z > boot_top - 0.06) & (R["handL"] < 0.1) & (R["handR"] < 0.1)

    def p_disp(P, N):
        d = np.zeros(len(P))
        for kn, an in ((kn_L, an_L), (kn_R, an_R)):
            side = np.sign(kn[0])
            hp = L["LeftUpLeg"] if side > 0 else L["RightUpLeg"]
            dd = ring_folds(P, hp, an, np.linalg.norm(kn - hp) + 0.01, 0.045, 0.024, 0.0018, inner=math.pi, seed=side, ref=(0, -1, 0))
            d += np.where(np.sign(P[:, 0]) == side, dd, 0)
        return d

    pants = shell(ctx, "Lyra_Pants", pants_m, lambda P, N: np.full(len(P), 0.0035) + 0.0025 * ss(0.4, 0.8, P[:, 2]), mats=("Garment_Pants",),
                  smooth=3, subdiv=0, rim=0.004, refine_fn=lambda P: np.abs(P[:, 2] - kn_L[2]) < 0.07, refine_iter=1, disp=p_disp)
    objs["Pants"] = pants

    # ------------------------------------------------------------------ cropped bomber jacket
    jhem = L["Spine2"][2] + 0.035
    j_m = (R["torso"] + R["uarmL"] + R["uarmR"]) > 0.5
    j_m &= (R["neck"] < 0.55) & (R["head"] < 0.02) & (z > jhem)
    tLw, _, _ = limb_coords(co, sh_L, wr_L)
    tRw, _, _ = limb_coords(co, sh_R, wr_R)
    j_m |= ((R["farmL"] > 0.4) & (tLw < ua + 0.05)) | ((R["farmR"] > 0.4) & (tRw < ua + 0.05))
    j_m &= ~((x > 0.2) & (tLw > ua + 0.05)) & ~((x < -0.2) & (tRw > ua + 0.05))
    j_m &= ~((np.abs(x) < 0.045 + 0.03 * ss(clav_z - 0.1, clav_z, z)) & (y < cy - 0.02))  # open front
    def j_off(P, N):
        o = np.full(len(P), 0.015)
        o += 0.005 * ss(1.38, 1.46, P[:, 2]) * (np.abs(P[:, 0]) < 0.3)
        return o

    def j_disp(P, N):
        d = np.zeros(len(P))
        for sh, el, s_ in ((sh_L, el_L, 1), (sh_R, el_R, -1)):
            t, ph, _ = limb_coords(P, sh, el)
            end = ua + 0.05
            m = (np.sign(P[:, 0]) == s_) & (np.abs(P[:, 0]) > 0.18)
            d += np.where(m, 0.007 * ss(end - 0.05, end - 0.01, t) * (0.6 + 0.4 * np.sin(ph * 3)), 0)  # pushed-up cuff bulge
            d += np.where(m, ring_folds(P, sh, el, ua - 0.01, 0.05, 0.022, 0.0028, inner=math.pi * 0.5, seed=s_), 0)
        d += 0.0008 * fbm(P, 8.0, 3, 3.0)
        return d

    jacket = shell(ctx, "Lyra_Jacket", j_m, j_off, mats=("Garment_Top",), smooth=5, subdiv=0, rim=0.006, bsmooth=14,
                   refine_fn=lambda P: (np.abs(P[:, 0]) > 0.15) & (P[:, 2] > 1.25), refine_iter=1, disp=j_disp)
    objs["Jacket"] = jacket
    gear.strip_occluded(suit, [jacket], 0.04, 1)
    # stand collar of the jacket (open at the front)
    col = Part("Lyra_JacketCollar")
    nc = np.array((0, L["Neck"][1] + 0.012, L["Neck"][2] - 0.07))
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector as V3
    neck_f = [i for i, f in enumerate(B.faces) if all(R["neck"][v] + R["torso"][v] > 0.5 and z[v] < L["Neck"][2] + 0.05 for v in f)]
    ntree = BVHTree.FromPolygons([V3(c_) for c_ in co], [B.faces[i] for i in neck_f])
    NC = 36
    base_r = []
    for k in range(NC):
        phi = 2 * math.pi * k / NC
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        hit, _ = ctx.cast(nc + d * 0.13, -d, 0.14, ntree)
        base_r.append(np.linalg.norm((hit - nc)[:2]) if hit is not None else 0.065)
    base_r = np.convolve(np.r_[base_r[-3:], base_r, base_r[:3]], np.ones(7) / 7, "valid")
    rows = []
    for hz, push in ((0.0, 0.02), (0.035, 0.022), (0.06, 0.026), (0.07, 0.03)):
        rows.append([nc + np.array((math.sin(2 * math.pi * k / NC), -math.cos(2 * math.pi * k / NC), 0)) * (base_r[k] + push)
                     + np.array((0, 0, hz * (1 - 0.35 * (0.5 + 0.5 * math.cos(2 * math.pi * k / NC))))) for k in range(NC)])
    V = np.array([p for r_ in rows for p in r_])
    F, U = [], []
    for ri in range(len(rows) - 1):
        for k in range(NC):
            if k in (NC - 2, NC - 1, 0, 1):
                continue
            k2 = (k + 1) % NC
            F.append([ri * NC + k, ri * NC + k2, ri * NC + k2 + NC, ri * NC + k + NC])
            U.append([(k / NC * 2, ri / 3), ((k + 1) / NC * 2, ri / 3), ((k + 1) / NC * 2, (ri + 1) / 3), (k / NC * 2, (ri + 1) / 3)])
    col.add(V, F, "Garment_Top", U, {"collar": 1.0})
    co_obj = col.build()
    m = co_obj.modifiers.new("solid", "SOLIDIFY"); m.thickness = 0.007; m.offset = -1.0
    gear.apply_modifiers(co_obj)
    for p_ in co_obj.data.polygons:
        p_.use_smooth = True
    objs["Jacket"] = jacket = gear.join([jacket, co_obj], "Lyra_Jacket")
    ctx.push_stack(jacket)

    # ------------------------------------------------------------------ boots
    boots_m = ((R["footL"] + R["footR"] + R["shinL"] + R["shinR"]) > 0.5) & (z < boot_top)
    objs["Boots"] = gear.remesh_envelope(ctx, "Lyra_Boots", boots_m, voxel=0.01, offset=0.007, smooth_iter=14, zmax=boot_top, floor_z=0.03, mat="Boots", gap=0.006, decimate=0.42)
    bco = gear.get_co(objs["Boots"])
    bp = Part("Lyra_BootsDetail")
    for an, s_ in ((an_L, 1), (an_R, -1)):
        sole(ctx, bp, bco[(np.sign(bco[:, 0]) == s_) & (bco[:, 2] < 0.04)], an)
    ctx.push_stack(objs["Boots"])
    for an, s_ in ((an_L, 1), (an_R, -1)):
        for zz, ww in ((an[2] + 0.1, 0.022), (an[2] + 0.17, 0.022), (an[2] + 0.235, 0.02)):
            P_, N_ = limb_ring(ctx, np.array((an[0], an[1] + 0.005, zz)), 25, R=0.1)
            strap(bp, P_, N_, ww, 0.003, mat="Boots", attrs={"strap": 1.0})
            i = 6 if s_ > 0 else 18
            buckle(bp, P_[i] + N_[i] * 0.003, P_[i + 1] - P_[i], N_[i], ww, mat="Metal")
        boot_armor(ctx, bp, an, L["LeftToeBase"] if s_ > 0 else L["RightToeBase"], s_, 0.85)
    objs["Boots"] = gear.join([objs["Boots"], bp.build()], "Lyra_Boots")

    # ------------------------------------------------------------------ fingerless gloves
    dwl = np.linalg.norm(co - wr_L, axis=1)
    dwr = np.linalg.norm(co - wr_R, axis=1)
    hand = (R["handL"] + R["handR"]) > 0.3
    # keep fingers bare beyond the first phalanx: distance from the wrist along the hand
    fingers = hand & (np.minimum(dwl, dwr) > 0.105)
    glove_m = (hand & ~fingers) | ((R["farmL"] > 0.3) & (dwl < 0.05)) | ((R["farmR"] > 0.3) & (dwr < 0.05))
    gloves = shell(ctx, "Lyra_Gloves", glove_m, lambda P, N: np.full(len(P), 0.0024), mats=("Gloves",), smooth=1, subdiv=0, rim=0.003,
                   stack=False, bsmooth=8)
    objs["Gloves"] = gloves

    tree = ctx.outer_tree()
    # ------------------------------------------------------------------ light right shoulder plate (on the jacket)
    sp = Part("Lyra_ShoulderR")
    piv = sh_R + np.array((0.035, 0, -0.045))
    plate(ctx, sp, sh_R + np.array((-0.04, 0, 0.065)), nrm(np.array((-0.78, 0, 0.66))), (0.66, 0, 0.78), 0.085, 0.08, mode="radial", pivot=piv,
          poly=[(-1, 0.4), (-0.4, 1), (0.7, 0.9), (1, 0.2), (0.8, -0.9), (-0.6, -1), (-1, -0.5)], corner=0.28, offset=0.012, thickness=0.006,
          crown=0.007, chamfer=0.003, groove=0.68, bolts=[(-0.5, 0.55), (0.55, 0.5)], plate_id=3, gasket="Gloves", cast_r=0.3, segs=40,
          zone=0, edge_zone=2, rivets=True, inlay=(0.12, 0.32), inlay_mat="Glow2")
    frames = []
    for k in range(2):
        t = 0.24 + 0.15 * k
        p_, n_ = ctx.limb_point("RightArm", t, math.radians(12), ref=(0, 0, 1), R=0.14)
        frames.append(plate(ctx, sp, p_, n_, nrm(sh_R - el_R), 0.062 - 0.006 * k, 0.025, mode="radial", pivot=L["RightArm"] + (el_R - sh_R) * t,
                            poly=[(-1, 1), (1, 1), (0.85, -1), (-0.85, -1)], corner=0.25, offset=0.02 + 0.005 * (1 - k), thickness=0.005,
                            crown=0.002, chamfer=0.0025, plate_id=4 + k, segs=28, cast_r=0.14, zone=1 if k == 0 else 0, edge_zone=2))
    for fr in frames:
        for sx in (-1, 1):
            h0, _ = fr["P"](sx * fr["a"] * 0.96, fr["b"] * 0.85, 0.004)
            h1, _ = fr["P"](sx * fr["a"] * 0.74, fr["b"] * 0.85, 0.004)
            gear.hinge(sp, h0, h1, 0.0032, 3)
    objs["ShoulderR"] = sp.build()

    # ------------------------------------------------------------------ holo bracer (left forearm)
    fg = Part("Lyra_ForearmGuardL")
    ax = nrm(wr_L - el_L)
    flen = np.linalg.norm(wr_L - el_L)
    for t0, t1, a_ in ((0.55, 0.9, 0.0),):
        tm = (t0 + t1) / 2
        c = el_L + (wr_L - el_L) * tm
        p_, n_ = ctx.limb_point("LeftForeArm", tm, math.radians(10), ref=(0, 0, 1), R=0.1)
        plate(ctx, fg, p_, n_, ax, 0.03, (t1 - t0) * flen * 0.5, mode="radial", pivot=c, poly=[(-1, 1), (1, 1), (0.9, -1), (-0.9, -1)], corner=0.2,
              offset=0.006, thickness=0.006, crown=0.003, chamfer=0.003, groove=0.66, plate_id=40, segs=28, cast_r=0.1, zone=1, edge_zone=2,
              rivets=True)
    # bracer bands
    for t in (0.56, 0.89):
        ring = [ctx.limb_point("LeftForeArm", t, 2 * math.pi * k / 20, push=0.004, ref=(0, 0, 1), R=0.1) for k in range(21)]
        strap(fg, np.array([p for p, _ in ring]), np.array([n for _, n in ring]), 0.012, 0.004, mat="Metal", attrs={"wear": 1.0}, caps=False)
    # screen + holo frame
    p_, n_ = ctx.limb_point("LeftForeArm", 0.72, math.radians(10), push=0.016, ref=(0, 0, 1), R=0.1)
    r_, u_, nn_ = gear.frame_from(n_, ax)
    rbox(fg, p_, r_, u_, nn_, (0.036, 0.06, 0.008), 0.003, 2, mat="Armor", attrs={"plate": 41.0, "mz": 2.0, "wear": 0.6})
    rbox(fg, p_ + nn_ * 0.0045, r_, u_, nn_, (0.028, 0.048, 0.0015), 0.0008, 1, mat="Screen")
    hc_ = p_ + nn_ * 0.028
    frame = [hc_ + r_ * 0.02 * sx + u_ * 0.032 * sy for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))]
    for a__, b__ in zip(frame[:-1], frame[1:]):
        tube(fg, [a__, b__], 0.0007, 4, mat="Glow2")
    for k in range(3):
        tube(fg, [hc_ - r_ * 0.014 + u_ * (0.018 - k * 0.012), hc_ + r_ * (0.004 + 0.006 * k) + u_ * (0.018 - k * 0.012)], 0.0005, 4, mat="Glow2")
    for k in range(2):
        tube(fg, [p_ + nn_ * 0.004 + r_ * (0.019 - 0.038 * k) + u_ * 0.0, hc_ + r_ * (0.02 - 0.04 * k) - u_ * 0.032], 0.0004, 4, mat="Glow2")
    objs["ForearmGuardL"] = fg.build()

    # ------------------------------------------------------------------ harness, chest unit, cables, hip module
    hz = L["Spine"][2] + 0.01
    hr = Part("Lyra_Harness")
    ring, nrms = [], []
    for k in range(41):
        phi = 2 * math.pi * k / 40
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        c = np.array((0, L["Hips"][1] + 0.005, hz))
        hit, nn = ctx.cast(c + d * 0.3, -d, 0.32)
        ring.append(hit + nn * 0.002 if hit is not None else c + d * 0.15)
        nrms.append(d)
    Pb, Nb = np.array(ring), np.array(nrms)
    strap(hr, Pb, Nb, 0.035, 0.005, mat="Harness", attrs={"strap": 1.0}, caps=False)
    # Left-side Aether harness: front and back straps over the LEFT shoulder, a support strap under the bust to the
    # right side, the core module on the left ribcage, cabling to the hip module and up over the shoulder, clips.
    cu_z = L["Spine2"][2] + 0.01
    hit, nn = ctx.cast(np.array((0.085, -0.5, cu_z)), (0, 1, 0), 0.6)
    cu = hit + nn * 0.012
    sh_top = np.array((0.11, -0.02, L["LeftShoulder"][2] + 0.035))
    routes = [
        [np.array((0.105, -0.15, 1.42)), np.array((0.1, -0.16, cu_z + 0.06)), cu, np.array((0.1, -0.13, hz + 0.05)), np.array((0.11, -0.1, hz))],
        [np.array((0.105, -0.15, 1.42)), np.array((0.12, -0.06, L["LeftShoulder"][2] + 0.04)), np.array((0.12, 0.06, 1.47)),
         np.array((0.1, 0.12, 1.3)), np.array((0.09, 0.12, hz + 0.02))],
        [cu + np.array((-0.02, 0, -0.02)), np.array((0.0, -0.16, cu_z - 0.04)), np.array((-0.1, -0.12, cu_z - 0.045)), np.array((-0.16, -0.02, cu_z - 0.04)),
         np.array((-0.12, 0.1, cu_z - 0.04))],
    ]
    for ri_, wp in enumerate(routes):
        P_, N_ = surface_path(ctx, wp, 30 if ri_ < 2 else 22, push=0.003)
        strap(hr, P_, N_, 0.03 if ri_ < 2 else 0.024, 0.0045, mat="Harness", attrs={"strap": 1.0})
        for j in ((6, 20) if ri_ < 2 else (8,)):
            buckle(hr, P_[j] + N_[j] * 0.003, P_[j + 1] - P_[j], N_[j], 0.03 if ri_ < 2 else 0.024)
    # data cables: core -> left hip module, core -> over the left shoulder to the back (rubber sleeve, metal ferrules)
    hm_p = Pb[8]
    for wp, rad in (([cu + np.array((0.02, -0.012, -0.03)), cu + np.array((0.05, -0.03, -0.09)), hm_p + np.array((0.0, -0.04, 0.03))], 0.0036),
                    ([cu + np.array((0.0, -0.012, 0.035)), np.array((0.12, -0.15, 1.40)), np.array((0.14, -0.08, L["LeftShoulder"][2] + 0.03)),
                      np.array((0.13, 0.05, 1.47))], 0.003),
                    ([cu + np.array((-0.03, -0.012, 0.0)), np.array((-0.02, -0.17, cu_z + 0.02)), np.array((-0.06, -0.16, cu_z + 0.07))], 0.0024)):
        P_, N_ = surface_path(ctx, wp, 22, push=0.011)
        tube(hr, P_, rad, 8, mat="Gloves", caps=True)
        for t in (2, 10, 18):
            tube(hr, [P_[t] - gear.tangents(P_)[t] * 0.004, P_[t] + gear.tangents(P_)[t] * 0.004], rad * 1.4, 8, mat="Metal")
    objs["Harness"] = hr.build()
    cu_p = Part("Lyra_ChestUnit")
    r_, u_, nn_ = gear.frame_from(nn, (0, 0, 1))
    rbox(cu_p, cu + nn_ * 0.004, r_, u_, nn_, (0.07, 0.078, 0.022), 0.007, 2, mat="Armor", attrs={"plate": 50.0, "mz": 1.0})
    rbox(cu_p, cu + nn_ * 0.0155, r_, u_, nn_, (0.054, 0.056, 0.005), 0.002, 2, mat="Armor", attrs={"plate": 51.0, "mz": 2.0, "wear": 0.8})
    tube(cu_p, [cu + nn_ * 0.016, cu + nn_ * 0.0215], 0.02, 20, mat="Armor", caps=False, attrs={"plate": 52.0, "mz": 2.0, "wear": 1.0})
    for sx in (-1, 1):
        gear.bolt(cu_p.hi, cu + nn_ * 0.018 + r_ * sx * 0.022 + u_ * 0.023, nn_, u_, 0.0028, 0.0014, 50.0, sides=10)
        gear.socket(cu_p.hi, cu + nn_ * 0.018 + r_ * sx * 0.022 - u_ * 0.024, nn_, u_, 0.0035, 0.0012)
    for k in range(4):   # clip clamps at the module corners
        a_ = math.pi / 4 + k * math.pi / 2
        rbox(cu_p, cu + nn_ * 0.008 + (r_ * math.cos(a_) * 0.037 + u_ * math.sin(a_) * 0.041), r_, u_, nn_, (0.008, 0.008, 0.012), 0.0015, 1,
             mat="Metal")
    objs["ChestUnit"] = cu_p.build()
    cc = Part("Lyra_ChestCore")
    tube(cc, [cu + nn_ * 0.019, cu + nn_ * 0.025], 0.0145, 20, mat="Glow", caps=True)
    tube(cc, [cu + nn_ * 0.0205, cu + nn_ * 0.0225], 0.0185, 20, mat="Glow2", caps=False)
    objs["ChestCore"] = cc.build()
    hm = Part("Lyra_HipModule")
    n_ = Nb[8]
    r_, u_, nn_ = gear.frame_from(n_, (0, 0, 1))
    c_ = hm_p + nn_ * 0.024 - u_ * 0.045
    rbox(hm, c_, r_, u_, nn_, (0.08, 0.11, 0.04), 0.007, 2, mat="Armor", attrs={"plate": 60.0, "mz": 1.0})
    rbox(hm, c_ + nn_ * 0.019 + u_ * 0.012, r_, u_, nn_, (0.066, 0.05, 0.004), 0.0015, 1, mat="Armor", attrs={"plate": 61.0, "mz": 2.0, "wear": 0.8})
    gear.vent(hm.hi, lambda x, y, h: (c_ + r_ * x + u_ * (y + 0.012) + nn_ * (0.021 + h), nn_), 0.0, 0.0, 0.05, 0.03, 5, 0.0, u_, r_)
    rbox(hm, c_ + nn_ * 0.021, r_, u_, nn_, (0.06, 0.006, 0.003), 0.0012, 1, mat="Glow2")
    rbox(hm, c_ + nn_ * 0.021 - u_ * 0.025, r_, u_, nn_, (0.06, 0.006, 0.003), 0.0012, 1, mat="Glow2")
    for sx in (-1, 1):
        gear.bolt(hm.hi, c_ + nn_ * 0.0205 + r_ * sx * 0.032 + u_ * 0.045, nn_, u_, 0.003, 0.0016, 60.0, sides=10)
    objs["HipModule"] = hm.build()

    # ------------------------------------------------------------------ right thigh rig (holster pouch + straps)
    tr = Part("Lyra_ThighRig")
    for zz in (0.66, 0.78):
        P_, N_ = limb_ring(ctx, np.array((L["RightUpLeg"][0] - 0.01 + (L["RightLeg"][0] - L["RightUpLeg"][0]) * ((1.0 - zz) / 0.46), -0.005, zz)), 25, R=0.14)
        strap(tr, P_, N_, 0.026, 0.004, mat="Strap", attrs={"strap": 1.0})
        buckle(tr, P_[6] + N_[6] * 0.003, P_[7] - P_[6], N_[6], 0.026)
    hit, nn2 = ctx.cast(np.array((-0.6, -0.01, 0.72)), (1, 0, 0), 0.6)
    if hit is not None:
        pouch(ctx, tr, hit, nrm(nn2), (0, 0, 1), 0.085, 0.13, 0.035, mat="Garment_Pants", plate_id=70)
    objs["ThighRig"] = tr.build()

    # ------------------------------------------------------------------ circuit traces (ConduitL glow, ConduitR glow2)
    for side, s_, mat in (("L", 1, "Glow"), ("R", -1, "Glow2")):
        cd = Part(f"Lyra_Conduit{side}")
        # midriff traces (between the jacket hem and the harness belt)
        for k in range(4):
            a0 = s_ * (0.35 + 0.18 * k)
            pts2 = circuit_paths(rng, (a0, jhem - 0.02), -math.pi / 2 + rng.uniform(-0.3, 0.3), 5, (0.012, 0.025))
            P3 = []
            for (ph, zz) in pts2:
                zz = max(zz, hz + 0.03)
                p, n = ctx.torso_point(zz, ph, push=0.0, tree=ctx.outer_tree())
                P3.append(p)
            P_, N_ = surface_path(ctx, P3, 3 + 6 * len(P3), push=0.0003, spline=False)
            light_strip(cd, P_, N_, 0.0022, 0.0011, mat=mat)
            bolt(cd, P_[-1], N_[-1], (0, 0, 1), 0.0028, 0.0011, 0.0, sides=10, mat=mat)
        # outer leg traces (hip to knee to boot)
        hp = L["LeftUpLeg"] if s_ > 0 else L["RightUpLeg"]
        an = an_L if s_ > 0 else an_R
        for k in range(2):
            ph0 = s_ * math.pi * (0.5 + 0.08 * k) + (math.pi if s_ < 0 else 0) * 0
            pts = []
            tt = 0.04 + 0.05 * k
            phc = s_ * (math.pi / 2) + (-0.12 + 0.24 * k)
            while tt < 0.92:
                p, n = ctx.limb_point("LeftUpLeg" if s_ > 0 else "RightUpLeg", tt, phc, ref=(0, -1, 0), end="LeftFoot" if s_ > 0 else "RightFoot", R=0.16)
                pts.append(p)
                tt += rng.uniform(0.04, 0.09)
                if rng.random() < 0.35:
                    phc += rng.choice([-1, 1]) * 0.18
            P_, N_ = surface_path(ctx, pts, 4 * len(pts), push=0.0003, spline=False)
            light_strip(cd, P_, N_, 0.002, 0.001, mat=mat)
        objs[f"Conduit{side}"] = cd.build()

    # ------------------------------------------------------------------ HUD monocle visor (optional) + cyberware
    vz = Part("Lyra_Visor")
    eL = L["LeftEye"]
    temple = np.array((0.075, eL[1] + 0.05, eL[2] + 0.004))
    hit, nn = ctx.cast(temple + np.array((0.2, 0, 0)), (-1, 0, 0), 0.3, ctx.tree)
    tp = (hit + nn * 0.003) if hit is not None else temple
    r_, u_, nn_ = gear.frame_from(np.array((1.0, 0, 0)), (0, 0, 1))
    rbox(vz, tp + np.array((0.004, 0.0, 0.0)), np.array((0, 1.0, 0)), np.array((0, 0, 1.0)), np.array((1.0, 0, 0)), (0.022, 0.012, 0.007), 0.0025, 2,
         mat="Armor", attrs={"plate": 80.0})
    rbox(vz, tp + np.array((0.0078, 0.0, 0.0)), np.array((0, 1.0, 0)), np.array((0, 0, 1.0)), np.array((1.0, 0, 0)), (0.014, 0.0018, 0.0012), 0.0004, 1, mat="Glow2")
    lens_c = np.array((eL[0] + 0.004, eL[1] - 0.03, eL[2] - 0.0085))
    arc = [tp + np.array((0.001, -0.01, -0.004)), np.array((eL[0] + 0.038, eL[1] - 0.012, eL[2] - 0.009)), lens_c + np.array((0.016, 0.004, 0.0))]
    tube(vz, np.array(gear.catmull(arc, 10)), 0.0013, 6, mat="Metal", caps=True)
    fwd = nrm(np.array((0.12, -1, 0.0)))
    r_, u_, nn_ = gear.frame_from(fwd, (0, 0, 1))
    rbox(vz, lens_c, r_, u_, nn_, (0.026, 0.0034, 0.0012), 0.0005, 1, mat="Metal")
    rbox(vz, lens_c + nn_ * 0.0007, r_, u_, nn_, (0.02, 0.0012, 0.0006), 0.0002, 1, mat="Screen")
    objs["Visor"] = vz.build()
    cw = Part("Lyra_Cyberware")
    eR = L["RightEye"]
    fwd = nrm(ctx.T["RightEye"] - eR)
    import bpy
    eo = next((o for o in bpy.data.objects if o.type == "MESH" and "high-poly" in o.name), None)
    apex = 0.0118
    if eo is not None:
        ev = np.array([v.co[:] for v in eo.data.vertices])
        ev = ev[ev[:, 0] < 0]
        apex = float(((ev - eR) @ fwd).max())
    # cyber-eye ring just in front of the right cornea (thin glowing limbal ring)
    ring_pts = []
    up0 = nrm(np.array((0, 0, 1.0)) - fwd * fwd[2]); rt = np.cross(fwd, up0)
    for k in range(25):
        a__ = 2 * math.pi * k / 24
        ring_pts.append(eR + fwd * (apex - 0.0016) + (up0 * math.cos(a__) + rt * math.sin(a__)) * 0.0058)
    tube(cw, np.array(ring_pts), 0.00035, 5, mat="Glow2")
    objs["Cyberware"] = cw.build()
    return objs
