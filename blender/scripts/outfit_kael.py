"""Kael Voss: cyberpunk vanguard / street samurai outfit (HD pipeline).

Armoured techwear jacket with a high collar and illuminated seams, layered plate-carrier chest rig, heavy
pauldrons, left chest plate, cargo techwear trousers with articulated knee armour, duty belt with modules,
heavy boots, tactical gloves with knuckle plates, a chrome/carbon exo-plated right forearm with the Aether
interface, and subtle facial cyberware. Mesh names follow the Unity contract (see export_hero.py).
"""
import math
import numpy as np
from mathutils import Vector
import gear
from gear import Part, nrm, ss, shell, plate, pouch, buckle, strap, surface_path, light_strip, tube, rbox, bolt, ring_folds, limb_coords, fbm, vnoise

NAME = "Kael"


def build(ctx):
    L, R = ctx.L, ctx.R if hasattr(ctx, "R") else ctx.region
    R = ctx.region
    B = ctx.B
    co = ctx.basis
    vn = ctx.vn
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    objs = {}
    hips_z = L["Hips"][2]
    sh_L, sh_R = L["LeftArm"], L["RightArm"]
    el_L, el_R = L["LeftForeArm"], L["RightForeArm"]
    wr_L, wr_R = L["LeftHand"], L["RightHand"]
    kn_L, kn_R = L["LeftLeg"], L["RightLeg"]
    an_L, an_R = L["LeftFoot"], L["RightFoot"]

    # ------------------------------------------------------------------ jacket (Top)
    hem_front = hips_z - 0.045
    hem_back = hips_z - 0.085
    hem = hem_front + (hem_back - hem_front) * ss(-0.05, 0.08, y)
    t_r, _, _ = limb_coords(co, sh_R, el_R)
    upper_R = np.linalg.norm(el_R - sh_R)
    jacket_m = (R["torso"] + R["uarmL"] + R["farmL"] + R["uarmR"] + R["farmR"] + R["hips"]) > 0.5
    jacket_m &= (R["handL"] < 0.3) & (R["handR"] < 0.3) & (R["neck"] < 0.55) & (R["head"] < 0.02)
    jacket_m &= z > hem
    jacket_m &= ~((x < -0.2) & (t_r > upper_R * 0.86))  # right sleeve ends above the elbow (exo forearm)
    jacket_m &= ~((x > 0.3) & (np.linalg.norm(co - wr_L, axis=1) < 0.035))

    def j_off(P, N):
        # fitted tactical cut: sleeves follow the arm (no inflated upper arms), slight padding on the yoke only
        o = np.full(len(P), 0.0085) + 0.0015 * ss(0.17, 0.24, np.abs(P[:, 0]))
        tor = (np.abs(P[:, 0]) < 0.2) & (P[:, 2] > hips_z)
        o[tor] += 0.003
        o += 0.003 * ss(1.38, 1.47, P[:, 2]) * (np.abs(P[:, 0]) < 0.24)  # padded yoke
        return o

    def j_refine(P):
        tl, _, _ = limb_coords(P, sh_L, wr_L)
        near_el = np.abs(tl - np.linalg.norm(el_L - sh_L)) < 0.09
        sho = (P[:, 2] > 1.36) & (np.abs(P[:, 0]) > 0.12) & (np.abs(P[:, 0]) < 0.34)
        return near_el | sho

    def j_disp(P, N):
        d = ring_folds(P, sh_L, wr_L, np.linalg.norm(el_L - sh_L), 0.05, 0.026, 0.0032, inner=math.pi * 0.5, seed=1.0)
        # shoulder/armpit drag folds
        for s_, sh in ((1, sh_L), (-1, sh_R)):
            q = P - sh
            m = np.exp(-((np.abs(P[:, 0]) - 0.2) / 0.06) ** 2) * np.exp(-((P[:, 2] - 1.4) / 0.06) ** 2)
            d += 0.0018 * m * np.sin(2 * math.pi * (q[:, 2] * 0.7 + q[:, 0] * s_ * 0.7) / 0.03)
        d += 0.0008 * fbm(P, 7.0, 3, 2.0)
        return d

    jacket = shell(ctx, "Kael_Top", jacket_m, j_off, mats=("Garment_Top",), smooth=5, subdiv=0, rim=0.006,
                   refine_fn=j_refine, refine_iter=1, disp=j_disp)
    objs["Top"] = jacket

    # ------------------------------------------------------------------ trousers (Pants)
    waist_z = L["Spine"][2] + 0.0
    boot_top = an_L[2] + 0.235
    pants_m = ((R["hips"] + R["thighL"] + R["thighR"] + R["shinL"] + R["shinR"] + R["torso"] * (z < waist_z)) > 0.5)
    pants_m &= (z < waist_z) & (z > boot_top - 0.06) & (R["handL"] < 0.1) & (R["handR"] < 0.1)

    def p_off(P, N):
        o = np.full(len(P), 0.010)
        o += 0.004 * ss(0.45, 0.85, P[:, 2]) * (1 - ss(0.9, 1.0, P[:, 2]))  # cargo thighs (kept athletic)
        return o

    def p_refine(P):
        kn = (np.abs(P[:, 2] - kn_L[2]) < 0.08)
        boot = P[:, 2] < boot_top + 0.09
        crotch = (P[:, 2] > hips_z - 0.15) & (P[:, 2] < hips_z - 0.02) & (np.abs(P[:, 0]) < 0.12)
        return kn | boot | crotch

    def p_disp(P, N):
        d = np.zeros(len(P))
        for kn, an in ((kn_L, an_L), (kn_R, an_R)):
            side = np.sign(kn[0])
            m = np.sign(P[:, 0]) == side
            hp = L["LeftUpLeg"] if side > 0 else L["RightUpLeg"]
            dd = ring_folds(P, hp, an, np.linalg.norm(kn - hp) + 0.01, 0.055, 0.03, 0.003, inner=math.pi, seed=side, ref=(0, -1, 0))
            # stacking above the boot top
            zb = P[:, 2] - boot_top
            env = np.exp(-((zb - 0.025) / 0.04) ** 2)
            t, phi, _ = limb_coords(P, hp, an, (0, -1, 0))
            dd += 0.0035 * env * np.sin(2 * math.pi * (zb / 0.024 + 0.3 * np.sin(phi * 3 + side)))
            d += np.where(m, dd, 0)
        d += 0.001 * fbm(P, 8.0, 3, 5.0)
        return d

    pants = shell(ctx, "Kael_Pants", pants_m, p_off, mats=("Garment_Pants",), smooth=4, subdiv=0, rim=0.005,
                  refine_fn=p_refine, refine_iter=1, disp=p_disp)
    objs["Pants"] = pants

    # ------------------------------------------------------------------ boots
    boots_m = ((R["footL"] + R["footR"] + R["shinL"] + R["shinR"]) > 0.5) & (z < boot_top)

    def b_off(P, N):
        o = np.full(len(P), 0.009)
        o += 0.004 * ss(0.12, 0.04, P[:, 2])  # chunkier foot
        return o

    objs["Boots"] = gear.remesh_envelope(ctx, "Kael_Boots", boots_m, voxel=0.011, offset=0.008, smooth_iter=14, zmax=boot_top,
                                         floor_z=0.034, mat="Boots", gap=0.007, decimate=0.42)
    boot_obj = objs["Boots"]
    bp = Part("Kael_BootsDetail")
    bco = gear.get_co(boot_obj)
    for an, toe, s_ in ((an_L, L["LeftToeBase"], 1), (an_R, L["RightToeBase"], -1)):
        sole(ctx, bp, bco[(np.sign(bco[:, 0]) == s_) & (bco[:, 2] < 0.045)], an)
    ctx.push_stack(boot_obj)
    tmp_tree = None
    for an, toe, s_ in ((an_L, L["LeftToeBase"], 1), (an_R, L["RightToeBase"], -1)):
        # Two straps with buckles over the instep and the shaft.
        for zz, ww in ((an[2] + 0.12, 0.028), (an[2] + 0.19, 0.026)):
            P_, N_ = limb_ring(ctx, np.array((an[0], an[1] + 0.005, zz)), 25, R=0.11)
            strap(bp, P_, N_, ww, 0.0035, mat="Boots", attrs={"strap": 1.0})
            i = 6 if s_ > 0 else 18
            buckle(bp, P_[i] + N_[i] * 0.003, P_[i + 1] - P_[i], N_[i], ww, mat="Metal")
        boot_armor(ctx, bp, an, toe, s_, 1.0)
    objs["BootsDetail"] = bp.build()

    # ------------------------------------------------------------------ gloves
    dwl = np.linalg.norm(co - wr_L, axis=1)
    dwr = np.linalg.norm(co - wr_R, axis=1)
    glove_m = ((R["handL"] + R["handR"]) > 0.3) | ((R["farmL"] > 0.3) & (dwl < 0.075)) | ((R["farmR"] > 0.3) & (dwr < 0.05))

    HF = {s_: gear.hand_frame(L, s_) for s_ in (1, -1)}

    def g_off(P, N):
        """Tactical glove: padded palm, knuckle volume, finger thickness tapering to the tips, snug cuff."""
        o = np.zeros(len(P))
        for s_ in (1, -1):
            wr, dors, fdir, mcp = HF[s_]
            m = np.sign(P[:, 0]) == s_
            el = el_L if s_ > 0 else el_R
            t = (P - wr) @ nrm(el - wr)                 # up the forearm
            along = (P - wr) @ fdir                      # towards the fingertips
            dn = N @ dors
            v = 0.0028 - 0.0012 * ss(0.09, 0.17, along)  # fingers taper towards the tips
            v += 0.0022 * ss(-0.2, -0.6, dn) * ss(0.11, 0.06, along) * ss(-0.01, 0.02, along)   # palm padding
            for k_ in mcp:                               # knuckle volume on the back of the hand
                v += 0.0035 * np.exp(-(np.linalg.norm(P - k_, axis=1) / 0.011) ** 2) * ss(0.0, 0.4, dn)
            v += 0.0014 * ss(0.2, 0.6, dn) * ss(0.0, 0.03, along) * ss(0.085, 0.06, along)      # back-of-hand pad
            v += 0.006 * ss(0.0, 0.045, t) * (1.0 if s_ > 0 else 0.4)                            # cuff
            o = np.where(m, v, o)
        return o

    gloves = shell(ctx, "Kael_Gloves", glove_m, g_off, mats=("Gloves",), smooth=1, subdiv=0, rim=0.003, stack=False, bsmooth=12)
    ctx.push_stack(gloves)
    kp = Part("Kael_GloveArmor")
    for s_ in (1, -1):
        wr, dors, fdir, mcp = HF[s_]
        if len(mcp) < 2:
            continue
        kc = np.mean(mcp, axis=0) - fdir * 0.004
        w_ = np.linalg.norm(mcp[0] - mcp[-1]) * 0.62 + 0.008
        plate(ctx, kp, kc, dors, fdir, w_, 0.0105, offset=0.0015, thickness=0.0045, crown=0.0015, chamfer=0.0016,
              poly=[(-1, 1), (1, 1), (1, -1), (-1, -1)], corner=0.35, mat_top="Armor", mat_edge="Armor", mat_wall="Gloves", plate_id=90,
              segs=24, cast_r=0.05, clearance=0.0015, bolts=[(-0.8, 0.0), (0.8, 0.0)], zone=1, edge_zone=2)
        bc = wr + fdir * 0.045
        plate(ctx, kp, bc, dors, fdir, 0.022, 0.02, offset=0.0015, thickness=0.004, crown=0.0015, chamfer=0.0015,
              poly=[(-0.8, 1), (0.8, 1), (1, -0.6), (0, -1), (-1, -0.6)], corner=0.3, groove=0.62, groove_depth=0.0007, mat_top="Armor",
              mat_edge="Armor", mat_wall="Gloves", plate_id=91, segs=24, cast_r=0.05, clearance=0.0015, zone=2, edge_zone=2)
    kpo = kp.build()
    gear.set_attr(kpo, "kplate", np.ones(len(kpo.data.vertices)))
    gloves = gear.join([gloves, kpo], "Kael_Gloves")
    objs["Gloves"] = gloves

    # ------------------------------------------------------------------ chest rig (plate carrier over the jacket)
    tree_j = ctx.outer_tree()
    t_aL, _, _ = limb_coords(co, sh_L, el_L)
    rig_m = (R["torso"] > 0.55) & (z > hips_z + 0.13) & (z < 1.47 - 0.04 * ss(0.1, 0.2, np.abs(x))) & (R["uarmL"] < 0.25) & (R["uarmR"] < 0.25)

    def rig_off(P, N):
        # thinner towards the waist so the torso tapers (athletic V rather than a barrel)
        return np.full(len(P), 0.025) + 0.005 * ss(0.12, 0.0, np.abs(P[:, 0])) - 0.01 * ss(hips_z + 0.26, hips_z + 0.14, P[:, 2])

    carrier = shell(ctx, "Kael_ChestRig", rig_m, rig_off, mats=("Garment_Top",), smooth=8, subdiv=0, rim=0.014, cover=False,
                    min_clear=0.02)
    objs["ChestRig"] = carrier
    print("JACKET faces hidden under the vest:", gear.strip_occluded(jacket, [carrier], 0.06, 1))
    cr = Part("Kael_ChestRigGear")
    # Shoulder straps (front panel top -> over the trapezius -> back panel).
    for s_ in (1, -1):
        wp = [np.array((s_ * 0.105, -0.16, 1.44)), np.array((s_ * 0.13, -0.10, 1.53)), np.array((s_ * 0.13, 0.0, 1.565)),
              np.array((s_ * 0.13, 0.09, 1.52)), np.array((s_ * 0.11, 0.13, 1.43))]
        P_, N_ = surface_path(ctx, wp, 22, push=0.002)
        strap(cr, P_, N_, 0.045, 0.006, mat="Belt", attrs={"strap": 1.0})
        buckle(cr, P_[4] + N_[4] * 0.004, P_[5] - P_[4], N_[4], 0.045)
    # Magazine / utility pouches on the lower front panel (right side) and a radio pouch (left) with an LED.
    tree_c = ctx.outer_tree()
    for i, xx in enumerate((-0.115, -0.06, -0.005)):
        hit, nn = ctx.cast(np.array((xx, -0.5, 1.255)), (0, 1, 0), 0.6, tree_c)
        if hit is not None:
            pouch(ctx, cr, hit - np.array((0, 0, 0.0)), nrm(nn * 0.5 + np.array((0, -1, 0))), (0, 0, 1), 0.05, 0.1, 0.03, mat="Garment_Top", plate_id=10 + i)
    hit, nn = ctx.cast(np.array((0.1, -0.5, 1.25)), (0, 1, 0), 0.6, tree_c)
    if hit is not None:
        c = pouch(ctx, cr, hit, nrm(nn * 0.5 + np.array((0, -1, 0))), (0, 0, 1), 0.07, 0.085, 0.035, mat="Garment_Top", snap=False, plate_id=13)
        n2 = nrm(nn * 0.5 + np.array((0, -1, 0)))
        rbox(cr, c + n2 * 0.019 + np.array((0.022, 0, 0.032)), np.array((1, 0, 0)), np.array((0, 0, 1)), n2, (0.008, 0.008, 0.004), 0.0015, 1, mat="Glow2")
        tube(cr, [c + np.array((-0.02, 0.0, 0.04)), c + np.array((-0.02, -0.004, 0.09)), c + np.array((-0.024, -0.006, 0.115))], 0.004, 6, mat="Metal")
    # Illuminated top edge of the carrier.
    P_, N_ = surface_path(ctx, [np.array((-0.16, -0.2, 1.43)), np.array((-0.05, -0.22, 1.46)), np.array((0.05, -0.22, 1.46)), np.array((0.16, -0.2, 1.43))], 28, push=0.0005)
    light_strip(cr, P_, N_, 0.003, 0.0015, mat="Glow")
    rg = cr.build()
    objs["ChestRigGear"] = rg
    ctx.push_stack(rg)

    # ------------------------------------------------------------------ layered chest armour + gorget + clavicle guards
    cp = Part("Kael_ChestPlate")
    cz = L["Spine2"][2] + 0.125
    piv = np.array((0.0, L["Spine2"][1] + 0.03, cz - 0.02))
    hit, nn = ctx.cast(np.array((0.0, -0.5, cz + 0.004)), (0, 1, 0), 0.6)
    # carbon under-layer peeking out around the breastplate (layered edge)
    plate(ctx, cp, hit, nrm(np.array((0, -1, 0.12))), (0, 0, 1), 0.162, 0.083, mode="radial", pivot=piv,
          poly=[(-1, 0.48), (-0.76, 1), (-0.24, 1), (0, 0.78), (0.24, 1), (0.76, 1), (1, 0.48), (0.9, -0.48), (0.36, -1), (-0.36, -1), (-0.9, -0.48)],
          corner=0.1, offset=0.005, thickness=0.005, crown=0.003, chamfer=0.0025, zone=1, edge_zone=2, plate_id=100, segs=60, cast_r=0.35, gasket="Gloves")
    # breastplate: angular, painted, groove with a short cyan inlay, rivets, vent grille, bolts
    plate(ctx, cp, hit, nrm(np.array((0, -1, 0.12))), (0, 0, 1), 0.148, 0.074, mode="radial", pivot=piv,
          poly=[(-1, 0.45), (-0.74, 1), (-0.22, 1), (0, 0.76), (0.22, 1), (0.74, 1), (1, 0.45), (0.88, -0.46), (0.34, -1), (-0.34, -1), (-0.88, -0.46)],
          corner=0.1, offset=0.0105, thickness=0.007, crown=0.004, chamfer=0.0034, groove=0.82, groove_depth=0.0015, ridge=0.0012,
          bolts=[(-0.78, 0.6), (0.78, 0.6), (-0.6, -0.62), (0.6, -0.62)], vents=[(0.42, -0.32, 0.26, 0.26, 4)], rivets=True,
          inlay=(0.53, 0.6), inlay_mat="Glow", zone=0, edge_zone=2, plate_id=1, segs=64, cast_r=0.35)
    # right accent plate (carbon) with a short magenta inlay
    hp, hn = ctx.cast(np.array((-0.085, -0.5, cz + 0.012)), (0, 1, 0), 0.6)
    plate(ctx, cp, hp, nrm(np.array((-0.3, -1, 0.15))), (0, 0, 1), 0.048, 0.03, mode="radial", pivot=piv,
          poly=[(-1, 1), (1, 1), (0.82, -1), (-1, -0.6)], corner=0.2, offset=0.018, thickness=0.005, crown=0.002, chamfer=0.0025, groove=0.68,
          inlay=(0.1, 0.2), inlay_mat="Glow2", zone=1, edge_zone=2, plate_id=2, segs=32, cast_r=0.35, bolts=[(0.7, 0.55)])
    # sternum keel with the Aether core socket
    hs_, hn_ = ctx.cast(np.array((0.0, -0.5, cz - 0.022)), (0, 1, 0), 0.6)
    fr = plate(ctx, cp, hs_, nrm(np.array((0, -1, 0.1))), (0, 0, 1), 0.017, 0.06, mode="radial", pivot=piv,
               poly=[(-1, 1), (1, 1), (1, -0.6), (0, -1), (-1, -0.6)], corner=0.3, offset=0.0185, thickness=0.006, crown=0.002, chamfer=0.0025,
               zone=2, edge_zone=2, plate_id=102, segs=28, cast_r=0.35, rivets=True)
    cc, cn = fr["P"](0.0, 0.026, 0.003)
    r_, u_, n_ = gear.frame_from(cn, (0, 0, 1))
    tube(cp, [cc - n_ * 0.002, cc + n_ * 0.0045], 0.0102, 16, mat="Armor", caps=False, attrs={"mz": 2.0, "wear": 1.0, "plate": 103.0})
    tube(cp, [cc + n_ * 0.0028, cc + n_ * 0.0038], 0.0076, 16, mat="Glow", caps=True)
    gear.socket(cp.hi, cc + n_ * 0.0047, n_, u_, 0.0102, 0.001)
    # clavicle guards (anodised) and a low gorget at the base of the collar
    nkc = np.array((0.0, L["Neck"][1] + 0.01, L["Neck"][2] - 0.05))
    for s_ in (1, -1):
        hcv, ncv = ctx.cast(np.array((s_ * 0.08, L["Neck"][1] + 0.0, L["Neck"][2] + 0.25)), (0, 0, -1), 0.4)
        if hcv is not None:
            plate(ctx, cp, hcv, nrm(ncv + np.array((s_ * 0.2, -0.2, 0.3))), (s_ * 1.0, 0, 0), 0.036, 0.026, offset=0.006, thickness=0.005,
                  crown=0.003, chamfer=0.0025, poly=[(-1, 1), (1, 0.8), (1, -1), (-1, -0.6)], corner=0.3, zone=2, edge_zone=2, plate_id=104,
                  segs=28, cast_r=0.15, bolts=[(0.0, 0.0)])
        plate(ctx, cp, nkc + np.array((s_ * 0.06, -0.045, 0.005)), nrm(np.array((s_ * 0.55, -0.82, 0.12))), (0, 0, 1), 0.036, 0.02,
              mode="radial", pivot=nkc, poly=[(-1, 1), (1, 1), (0.85, -1), (-0.85, -1)], corner=0.3, offset=0.028, thickness=0.005,
              crown=0.002, chamfer=0.0025, zone=0, edge_zone=2, plate_id=101, segs=28, cast_r=0.2, rivets=False)
    objs["ChestPlate"] = cp.build()

    # ------------------------------------------------------------------ pauldrons (shoulder cap + samurai-style lames)
    for side, s_ in (("L", 1), ("R", -1)):
        sh = sh_L if s_ > 0 else sh_R
        big = 0.84 if s_ > 0 else 0.7   # caps sit on the deltoid, not shells sticking out
        bone = "LeftArm" if s_ > 0 else "RightArm"
        piv = sh + np.array((-s_ * 0.035, 0.0, -0.045))
        pp = Part(f"Kael_Pauldron{side}")
        c = sh + np.array((s_ * 0.035, 0.0, 0.062))
        plate(ctx, pp, c, nrm(np.array((s_ * 0.72, 0, 0.7))), (-s_ * 0.7, 0, 0.72), 0.125 * big, 0.115 * big, mode="radial", pivot=piv,
              poly=[(-1, 0.55), (-0.45, 1), (0.6, 1), (1, 0.35), (1, -0.75), (0.5, -1), (-0.5, -1), (-1, -0.6)], corner=0.3,
              offset=0.011, thickness=0.008, crown=0.01, chamfer=0.0035, groove=0.66, groove_depth=0.0018, ridge=0.004,
              bolts=[(-0.62, 0.62), (0.62, 0.62), (0.0, -0.78)], plate_id=3, gasket="Gloves", cast_r=0.3, segs=48,
              zone=0, edge_zone=2, rivets=True, vents=[(0.15, -0.42, 0.42, 0.22, 4)], inlay=(0.08, 0.3), inlay_mat="Glow")
        if s_ > 0:
            # Raised collar guard (upturned flange on the inner edge of the left shoulder).
            plate(ctx, pp, sh + np.array((-0.085, 0.005, 0.085)), nrm(np.array((0.45, 0, 0.9))), (0, -1, 0.0), 0.03, 0.085,
                  poly=[(-1, 1), (1, 0.8), (1, -0.8), (-1, -1)], corner=0.35, mode="radial", pivot=sh + np.array((-0.13, 0, -0.04)),
                  offset=0.026, thickness=0.006, crown=0.003, chamfer=0.003, plate_id=4, segs=28, cast_r=0.3, bolts=[(0, 0.6), (0, -0.6)],
                  zone=1, edge_zone=2)
        objs[f"Pauldron{side}"] = pp.build()
        lp = Part(f"Kael_PauldronLame{side}")
        nl = 2
        frames = []
        for k in range(nl):
            t = 0.2 + 0.17 * k
            p_, n_ = ctx.limb_point(bone, t, math.radians(-12 * s_), ref=(0, 0, 1), R=0.14)
            axp = L[bone] + (ctx.T[bone] - L[bone]) * t
            up_ = nrm(L[bone] - ctx.T[bone])
            frames.append(plate(ctx, lp, p_, n_, up_, (0.085 - 0.004 * k) * big, 0.036 * big, mode="radial", pivot=axp,
                  poly=[(-1, 1), (1, 1), (1, -0.7), (0.8, -1), (-0.8, -1), (-1, -0.7)], corner=0.2,
                  offset=0.011 + 0.004 * (nl - k), thickness=0.0055, crown=0.003, chamfer=0.003, groove=0.62 if k == 0 else 0.0,
                  bolts=[(-0.82, 0.4), (0.82, 0.4)], plate_id=5 + k, segs=32, cast_r=0.14, zone=0 if k % 2 == 0 else 1, edge_zone=2))
        # hinge knuckles at both ends of each lame's upper edge, and a hydraulic piston down the outer side
        for k, fr in enumerate(frames):
            a_, b_ = fr["a"], fr["b"]
            for sx in (-1, 1):
                h0, hn0 = fr["P"](sx * a_ * 0.97, b_ * 0.88, 0.0045)
                h1, _ = fr["P"](sx * a_ * 0.72, b_ * 0.88, 0.0045)
                gear.hinge(lp, h0, h1, 0.0038 * big, 3)
        pa, pn = frames[0]["P"](frames[0]["a"] * 0.86 * (1 if s_ > 0 else 1), frames[0]["b"] * 0.6, 0.009)
        pb, _ = frames[-1]["P"](frames[-1]["a"] * 0.86, -frames[-1]["b"] * 0.3, 0.009)
        gear.piston(lp, pa, pb, 0.0042 * big, 0.002 * big)
        objs[f"PauldronLame{side}"] = lp.build()

    # ------------------------------------------------------------------ knee armour
    for side, s_ in (("L", 1), ("R", -1)):
        kn = kn_L if s_ > 0 else kn_R
        kp = Part(f"Kael_KneePad{side}")
        piv = kn + np.array((0, 0.03, 0.0))
        plate(ctx, kp, kn + np.array((0, -0.06, 0.01)), nrm(np.array((s_ * 0.08, -1, 0.05))), (0, 0, 1), 0.058, 0.07, n_exp=3.0, mode="radial", pivot=piv,
              offset=0.012, thickness=0.008, crown=0.008, chamfer=0.0035, groove=0.68, ridge=0.003, bolts=[(-0.7, 0.6), (0.7, 0.6)], plate_id=7, gasket="Gloves", cast_r=0.14,
              zone=0, edge_zone=2, rivets=True, vents=[(0.0, -0.45, 0.6, 0.22, 4)], inlay=(0.2, 0.3), inlay_mat="Glow")
        plate(ctx, kp, kn + np.array((0, -0.06, 0.1)), nrm(np.array((s_ * 0.05, -1, 0.15))), (0, 0, 1), 0.05, 0.028, n_exp=5.0, mode="radial",
              pivot=piv + np.array((0, 0, 0.09)), offset=0.01, thickness=0.006, crown=0.002, chamfer=0.0028, plate_id=8, segs=28, cast_r=0.14,
              zone=1, edge_zone=2)
        for sx in (1, -1):   # pivot discs on both sides of the knee
            hp_, hn_ = ctx.cast(np.array((kn[0] + sx * 0.25, kn[1], kn[2])), (-sx, 0, 0), 0.3)
            if hp_ is not None:
                tube(kp, [hp_ + hn_ * 0.001, hp_ + hn_ * 0.008], 0.014, 14, mat="Armor", caps=True, attrs={"mz": 2.0, "wear": 0.8, "plate": 9.0})
                gear.socket(kp.hi, hp_ + hn_ * 0.0082, hn_, (0, 0, 1), 0.007, 0.0015)
        # Strap behind the knee.
        for dz in (0.06, -0.05):
            P_, N_ = limb_ring(ctx, np.array((kn[0], kn[1], kn[2] + dz)), 17, R=0.12, phi0=math.pi * 0.42, phi1=math.pi * 1.58)
            strap(kp, P_, N_, 0.025, 0.004, mat="Belt", attrs={"strap": 1.0})
        objs[f"KneePad{side}"] = kp.build()

    # ------------------------------------------------------------------ belt with modules
    bt = Part("Kael_Belt")
    bz = hips_z + 0.06
    ring, nrms = [], []
    for k in range(49):
        phi = 2 * math.pi * k / 48
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        c = np.array((0, L["Hips"][1] + 0.01, bz))
        hit, nn = ctx.cast(c + d * 0.3, -d, 0.32)
        ring.append(hit + nn * 0.002 if hit is not None else c + d * 0.17)
        nrms.append(nrm(np.array((d[0], d[1], 0))))
    P_, N_ = np.array(ring), np.array(nrms)
    for _ in range(3):
        P_[1:-1] = P_[1:-1] * 0.5 + (P_[:-2] + P_[2:]) * 0.25
    strap(bt, P_, N_, 0.05, 0.007, mat="Belt", attrs={"strap": 1.0}, caps=False)
    # Buckle plate with a glow line.
    f0, n0 = P_[0], N_[0]
    rbox(bt, f0 + n0 * 0.01, np.array((1, 0, 0)), np.array((0, 0, 1)), n0, (0.07, 0.052, 0.01), 0.003, 2, mat="Metal", attrs={"wear": 1.0})
    rbox(bt, f0 + n0 * 0.0158, np.array((1, 0, 0)), np.array((0, 0, 1)), n0, (0.05, 0.006, 0.002), 0.001, 1, mat="Glow")
    for (k, kind) in ((8, "pouch"), (14, "box"), (31, "canister"), (37, "pouch"), (42, "pouch")):
        p, n = P_[k], N_[k]
        if kind == "pouch":
            pouch(ctx, bt, p - np.array((0, 0, 0.03)), n, (0, 0, 1), 0.06, 0.08, 0.026, mat="Garment_Pants", plate_id=20 + k)
        elif kind == "box":
            r_, u_, n_ = gear.frame_from(n, (0, 0, 1))
            rbox(bt, p + n * 0.026 - u_ * 0.025, r_, u_, n_, (0.075, 0.1, 0.042), 0.006, 2, mat="Armor", attrs={"plate": 30.0})
            rbox(bt, p + n * 0.048 - u_ * 0.012, r_, u_, n_, (0.05, 0.012, 0.004), 0.0015, 1, mat="Glow")
        else:
            r_, u_, n_ = gear.frame_from(n, (0, 0, 1))
            c = p + n * 0.032 - u_ * 0.02
            tube(bt, [c - u_ * 0.06, c + u_ * 0.05], 0.022, 14, mat="Metal", caps=True)
            tube(bt, [c - u_ * 0.012, c + u_ * 0.012], 0.0232, 14, mat="Glow")
    objs["Belt"] = bt.build()

    # ------------------------------------------------------------------ high collar
    col = Part("Kael_Collar")
    neck_f = [i for i, f in enumerate(B.faces) if all(R["neck"][v] + R["torso"][v] > 0.5 and z[v] < L["Neck"][2] + 0.06 for v in f)]
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector as V3
    ntree = BVHTree.FromPolygons([V3(c_) for c_ in co], [B.faces[i] for i in neck_f])
    z0 = L["Neck"][2] - 0.065
    nc = np.array((0, L["Neck"][1] + 0.015, z0))
    base_r = []
    NC = 40
    for k in range(NC):
        phi = 2 * math.pi * k / NC
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        hit, nn = ctx.cast(nc + d * 0.14, -d, 0.15, ntree)
        base_r.append(np.linalg.norm((hit - nc)[:2]) if hit is not None else 0.075)
    base_r = np.array(base_r)
    base_r = np.convolve(np.r_[base_r[-3:], base_r, base_r[:3]], np.ones(7) / 7, "valid")
    rows = []
    prof = [(0.0, 0.016), (0.035, 0.019), (0.07, 0.021), (0.095, 0.026), (0.105, 0.031)]
    for (hz, push) in prof:
        row = []
        for k in range(NC):
            phi = 2 * math.pi * k / NC
            d = np.array((math.sin(phi), -math.cos(phi), 0.0))
            front = 0.5 + 0.5 * math.cos(phi)  # 1 at the front
            hh = hz * (1 - 0.42 * front)       # lower at the front so it clears the jaw
            row.append(nc + d * (base_r[k] + push + 0.012 * front * (hz / 0.105)) + np.array((0, 0, hh)))
        rows.append(row)
    V = np.array([p for r_ in rows for p in r_])
    F, U = [], []
    gap = 2  # asymmetric opening on the character's left front (start of the diagonal closure)
    for ri in range(len(rows) - 1):
        for k in range(NC):
            if k in (NC - 1, 0, 1)[:gap]:
                continue
            k2 = (k + 1) % NC
            a_, b_ = ri * NC + k, ri * NC + k2
            F.append([a_, b_, b_ + NC, a_ + NC]); U.append([(k / NC * 2, ri / 4), ((k + 1) / NC * 2, ri / 4), ((k + 1) / NC * 2, (ri + 1) / 4), (k / NC * 2, (ri + 1) / 4)])
    col.add(V, F, "Garment_Top", U, {"collar": 1.0})
    co_obj = col.build()
    m = co_obj.modifiers.new("solid", "SOLIDIFY"); m.thickness = 0.009; m.offset = -1.0; m.use_even_offset = True
    gear.apply_modifiers(co_obj)
    for p_ in co_obj.data.polygons:
        p_.use_smooth = True
    objs["Collar"] = co_obj
    ctx.push_stack(co_obj)

    # ------------------------------------------------------------------ illuminated seams (Conduit)
    cd = Part("Kael_Conduit")
    tj = ctx.outer_tree()
    # Diagonal closure from the left collar to the right hip.
    a = np.array((0.07, -0.2, 1.52)); b = np.array((-0.13, -0.2, hips_z + 0.0))
    wp = [a + (b - a) * t for t in np.linspace(0, 1, 6)]
    P_, N_ = surface_path(ctx, wp, 40, push=0.0)
    light_strip(cd, P_, N_, 0.0035, 0.0016, mat="Glow")
    # Front yoke seams.
    for s_ in (1, -1):
        P_, N_ = surface_path(ctx, [np.array((s_ * 0.06, -0.2, 1.47)), np.array((s_ * 0.16, -0.17, 1.465)), np.array((s_ * 0.24, -0.1, 1.47))], 18)
        light_strip(cd, P_, N_, 0.0025, 0.0012, mat="Glow")
    # Back yoke chevron.
    P_, N_ = surface_path(ctx, [np.array((-0.2, 0.12, 1.45)), np.array((0.0, 0.14, 1.38)), np.array((0.2, 0.12, 1.45))], 28)
    light_strip(cd, P_, N_, 0.003, 0.0014, mat="Glow")
    # Left sleeve outer seam (shoulder -> cuff).
    pts = [ctx.limb_point("LeftArm", t, math.pi * 0.5, ref=(0, 0, 1))[0] for t in np.linspace(0.15, 1.0, 6)]
    pts += [ctx.limb_point("LeftForeArm", t, math.pi * 0.5, ref=(0, 0, 1))[0] for t in np.linspace(0.1, 0.8, 5)]
    P_, N_ = surface_path(ctx, pts, 40)
    light_strip(cd, P_, N_, 0.0025, 0.0012, mat="Glow")
    # Magenta detail: LED dashes on the left cuff and the collar.
    for t in (0.84, 0.88, 0.92):
        p, n = ctx.limb_point("LeftForeArm", t, math.pi * 0.15, ref=(0, 0, 1))
        r_, u_, n_ = gear.frame_from(n, wr_L - el_L)
        rbox(cd, p + n_ * 0.002, r_, u_, n_, (0.012, 0.004, 0.003), 0.001, 1, mat="Glow2")
    objs["Conduit"] = cd.build()

    # ------------------------------------------------------------------ exo-plated right forearm + interface
    fa = Part("Kael_ForearmGuardR")
    ax = nrm(wr_R - el_R)
    flen = np.linalg.norm(wr_R - el_R)
    # Carbon under-frame strips and chrome plates over the dorsal and outer side; inner forearm skin stays visible.
    segs_t = [(0.08, 0.36), (0.38, 0.64), (0.66, 0.9)]
    for si, (t0, t1) in enumerate(segs_t):
        tm = (t0 + t1) * 0.5
        c = el_R + (wr_R - el_R) * tm
        p, n = ctx.limb_point("RightForeArm", tm, math.radians(-20), ref=(0, 0, 1))
        plate(ctx, fa, p, n, ax, 0.032 - si * 0.002, (t1 - t0) * flen * 0.5, n_exp=6.0, mode="radial", pivot=c, offset=0.006, thickness=0.006,
              crown=0.003, chamfer=0.003, groove=0.62 if si == 1 else 0.0, mat_top="Armor", mat_edge="Armor", mat_wall="Armor", plate_id=40 + si, segs=28, cast_r=0.1,
              bolts=[(-0.8, 0.0), (0.8, 0.0)] if si != 1 else [], zone=2, edge_zone=2, rivets=si != 1)
        p2, n2 = ctx.limb_point("RightForeArm", tm, math.radians(-95), ref=(0, 0, 1))
        plate(ctx, fa, p2, n2, ax, 0.022, (t1 - t0) * flen * 0.45, n_exp=5.0, mode="radial", pivot=c, offset=0.005, thickness=0.005,
              crown=0.002, chamfer=0.0025, mat_top="Armor", mat_edge="Armor", mat_wall="Armor", plate_id=43 + si, segs=24, cast_r=0.1, zone=1, edge_zone=2)
    # Glow lines in the gaps between plates and down the outer side.
    for t in (0.37, 0.65):
        pts = [ctx.limb_point("RightForeArm", t, math.radians(a_), push=0.0045, ref=(0, 0, 1))[0] for a_ in np.linspace(-150, 30, 9)]
        nn_ = [ctx.limb_point("RightForeArm", t, math.radians(a_), ref=(0, 0, 1))[1] for a_ in np.linspace(-150, 30, 9)]
        light_strip(fa, np.array(pts), np.array(nn_), 0.0025, 0.0012, mat="Glow")
    pts = [ctx.limb_point("RightForeArm", t, math.radians(-58), push=0.004, ref=(0, 0, 1)) for t in np.linspace(0.06, 0.95, 16)]
    light_strip(fa, np.array([p for p, _ in pts]), np.array([n for _, n in pts]), 0.0022, 0.0012, mat="Glow")
    # Elbow joint cap and wrist ring.
    pe, ne = ctx.limb_point("RightArm", 0.98, math.radians(180), ref=(0, 0, 1))
    plate(ctx, fa, pe, nrm(ne + nrm(el_R - wr_R) * 0.6), (0, 0, 1), 0.034, 0.034, n_exp=2.0, mode="radial", pivot=el_R, offset=0.008, thickness=0.007,
          crown=0.006, chamfer=0.003, groove=0.6, mat_top="Armor", plate_id=46, segs=28, bolts=[(0, 0)], cast_r=0.1, zone=2, edge_zone=2)
    ring = [ctx.limb_point("RightForeArm", 0.95, 2 * math.pi * k / 20, push=0.006, ref=(0, 0, 1)) for k in range(21)]
    P_ = np.array([p for p, _ in ring]); N_ = np.array([n for _, n in ring])
    strap(fa, P_, N_, 0.016, 0.005, mat="Metal", attrs={"wear": 1.0}, caps=False)
    objs["ForearmGuardR"] = fa.build()
    itf = Part("Kael_Interface")
    p, n = ctx.limb_point("RightForeArm", 0.6, math.radians(-20), push=0.013, ref=(0, 0, 1))
    r_, u_, n_ = gear.frame_from(n, ax)
    rbox(itf, p, r_, u_, n_, (0.048, 0.084, 0.013), 0.004, 2, mat="Armor", attrs={"plate": 50.0, "mz": 1.0})          # carbon housing
    rbox(itf, p + n_ * 0.0068, r_, u_, n_, (0.041, 0.072, 0.003), 0.0012, 1, mat="Armor", attrs={"plate": 51.0, "mz": 2.0, "wear": 0.8})  # bezel
    rbox(itf, p + n_ * 0.0086, r_, u_, n_, (0.033, 0.058, 0.0012), 0.0004, 1, mat="Screen")                            # tinted glass screen
    for k in range(3):                                                                                                     # side keys
        rbox(itf, p + r_ * 0.0255 + u_ * (0.012 - k * 0.012) + n_ * 0.002, r_, u_, n_, (0.004, 0.008, 0.005), 0.001, 1, mat="Metal")
    rbox(itf, p - r_ * 0.0215 + n_ * 0.0075, r_, u_, n_, (0.0016, 0.06, 0.0016), 0.0004, 1, mat="Glow")                 # status strip
    for e in (-1, 1):
        gear.socket(itf.hi, p + u_ * e * 0.036 + n_ * 0.0066, n_, u_, 0.0038, 0.0012)
    # conduits from the interface to the elbow and to the wrist emitter (glow core in a segmented sleeve)
    for ang0, (t0, t1) in ((-55, (0.12, 0.52)), (-55, (0.68, 0.9)), (-2, (0.12, 0.52))):
        pts = [ctx.limb_point("RightForeArm", t, math.radians(ang0), push=0.0075, ref=(0, 0, 1)) for t in np.linspace(t0, t1, 10)]
        P_ = np.array([q for q, _ in pts]); N_ = np.array([w for _, w in pts])
        tube(itf, P_, 0.0019, 8, mat="Glow", caps=True)
        for j in range(1, 9, 2):
            tube(itf, [P_[j] - gear.tangents(P_)[j] * 0.003, P_[j] + gear.tangents(P_)[j] * 0.003], 0.0028, 8, mat="Armor", caps=True,
                 attrs={"mz": 2.0, "wear": 0.8, "plate": 52.0})
    # wrist emitter: anodised housing, glowing lens, three focusing prongs pointing along the hand
    pe_, ne_ = ctx.limb_point("RightForeArm", 0.93, math.radians(-20), push=0.009, ref=(0, 0, 1))
    r2, u2, n2 = gear.frame_from(ne_, ax)
    tube(itf, [pe_ - n2 * 0.004, pe_ + n2 * 0.009], 0.0125, 16, mat="Armor", caps=True, attrs={"mz": 2.0, "wear": 1.0, "plate": 53.0})
    tube(itf, [pe_ + n2 * 0.0088, pe_ + n2 * 0.0098], 0.0088, 16, mat="Glow", caps=True)
    tube(itf, [pe_ + n2 * 0.0086, pe_ + n2 * 0.0101], 0.0125, 16, mat="Armor", caps=False, attrs={"mz": 1.0, "plate": 53.0})
    for k in range(3):
        a_ = 2 * math.pi * k / 3 + 0.5
        base_ = pe_ + n2 * 0.007 + (r2 * math.cos(a_) + u2 * math.sin(a_)) * 0.0125
        tip_ = base_ + ax * 0.022 + n2 * 0.004 - (r2 * math.cos(a_) + u2 * math.sin(a_)) * 0.004
        tube(itf, [base_, tip_], 0.0016, 6, mat="Metal", caps=True)
    objs["Interface"] = itf.build()

    # ------------------------------------------------------------------ facial cyberware
    cw = Part("Kael_Cyberware")
    for k in range(3):
        a_ = np.array((0.072, -0.095 + 0.0, 1.775 - k * 0.011))
        hit, nn = ctx.cast(a_ + np.array((0.2, -0.05, 0)), nrm(np.array((-1, 0.25, 0))), 0.4, ctx.tree)
        if hit is None:
            continue
        P_, N_ = surface_path(ctx, [hit + np.array((0, 0.005 * k, 0)), hit + np.array((0.0, 0.03 + 0.006 * k, 0.004))], 6, tree=ctx.tree, push=0.0008)
        light_strip(cw, P_, N_, 0.0016, 0.0004, mat="Glow")
        bolt(cw, P_[0] + N_[0] * 0.0002, N_[0], (0, 0, 1), 0.0018, 0.0006, 60.0, sides=8, mat="Metal")
    # Neck port below the left ear.
    hit, nn = ctx.cast(np.array((0.3, -0.04, 1.63)), nrm(np.array((-1, 0, 0.1))), 0.4, ctx.tree)
    if hit is not None:
        r_, u_, n_ = gear.frame_from(nn, (0, 0, 1))
        tube(cw, [hit - n_ * 0.001, hit + n_ * 0.0025], 0.0075, 14, mat="Metal", caps=True)
        tube(cw, [hit + n_ * 0.0024, hit + n_ * 0.0032], 0.0045, 14, mat="Glow", caps=True)
    objs["Cyberware"] = cw.build()
    return objs


def boot_armor(ctx, bp, an, toe, s_, k=1.0):
    """Layered shin guard (painted over carbon), moulded toe cap and heel counter (polymer), on the boot envelope."""
    hit, nn = ctx.cast(np.array((an[0], an[1] - 0.3, an[2] + 0.17 * k)), (0, 1, 0), 0.4)
    piv = np.array((an[0], an[1] + 0.01, an[2] + 0.17 * k))
    if hit is not None:
        plate(ctx, bp, hit, nrm(nn + np.array((0, -0.3, 0))), (0, 0, 1), 0.034 * k, 0.07 * k, offset=0.004, thickness=0.005, crown=0.004,
              chamfer=0.0025, poly=[(-1, 1), (1, 1), (0.9, -0.5), (0, -1), (-0.9, -0.5)], corner=0.25, mode="radial", pivot=piv, cast_r=0.12,
              plate_id=71, segs=32, mat_top="Armor", mat_edge="Armor", mat_wall="Armor", zone=1, edge_zone=2, rivets=True)
        plate(ctx, bp, hit + np.array((0, -0.004, 0.012 * k)), nrm(nn + np.array((0, -0.3, 0))), (0, 0, 1), 0.026 * k, 0.045 * k, offset=0.011,
              thickness=0.005, crown=0.004, chamfer=0.0025, poly=[(-1, 1), (1, 1), (0.85, -0.6), (0, -1), (-0.85, -0.6)], corner=0.25,
              mode="radial", pivot=piv, cast_r=0.12, plate_id=70, segs=28, mat_top="Armor", mat_edge="Armor", mat_wall="Armor", zone=0,
              edge_zone=2, groove=0.66, inlay=(0.6, 0.9), inlay_mat="Glow", bolts=[(-0.7, 0.7), (0.7, 0.7)])
    hh, hn = ctx.cast(np.array((an[0], an[1] + 0.35, 0.06)), (0, -1, 0), 0.5)
    if hh is not None:
        plate(ctx, bp, hh, hn, (0, 0, 1), 0.04 * k, 0.034 * k, n_exp=2.8, offset=0.002, thickness=0.004, crown=0.0, chamfer=0.002,
              mat_top="Boots", mat_edge="Boots", mat_wall="Boots", segs=28, clearance=0.0012, cast_r=0.12, attrs={"cap": 1.0}, plate_id=73,
              mode="radial", pivot=np.array((an[0], an[1] - 0.01, 0.06)))


def limb_ring(ctx, c, n=25, R=0.13, push=0.001, phi0=0.0, phi1=2 * math.pi, axis_xy=None):
    """Horizontal ring of surface points around a vertical-ish limb centred at c (rays limited to R)."""
    pts, nrms = [], []
    for k in range(n):
        phi = phi0 + (phi1 - phi0) * k / (n - 1)
        d = np.array((math.sin(phi), -math.cos(phi), 0.0))
        hit, nn = ctx.cast(c + d * R, -d, R + 0.01)
        p = hit + nn * push if hit is not None else c + d * 0.07
        pts.append(p)
        nrms.append(nrm(np.array((p[0] - c[0], p[1] - c[1], 0.0))))
    return np.array(pts), np.array(nrms)


def sole(ctx, part, bottom_pts, an):
    """Chunky cupsole around the boot's lower edge: bevelled slab, raised heel, toe spring and side lugs."""
    P = bottom_pts
    cx, cy = an[0], (P[:, 1].min() + P[:, 1].max()) * 0.5
    n = 44
    outline = []
    for k in range(n):
        phi = 2 * math.pi * k / n
        d = np.array((math.sin(phi), -math.cos(phi)))
        proj = (P[:, :2] - np.array((cx, cy))) @ d
        outline.append(np.array((cx, cy)) + d * (np.percentile(proj, 98) + 0.004))
    outline = np.array(outline)
    for _ in range(4):
        outline = outline * 0.5 + (np.roll(outline, 1, 0) + np.roll(outline, -1, 0)) * 0.25
    ymin, ymax = outline[:, 1].min(), outline[:, 1].max()
    verts, faces, uvs, sharp = [], [], [], []
    rings = [(0.0, 0.0), (0.0035, -0.004), (0.006, -0.012), (0.004, -0.026), (0.0, -0.034), (-0.008, -0.036)]  # (outset, dz from top)
    for (ox, oy) in outline:
        heel = ss(ymax - 0.09, ymax - 0.03, oy)
        spring = 0.014 * ss(ymin + 0.07, ymin, oy)
        top = 0.04 + 0.012 * heel + spring * 0.3
        bottom = -0.002 + spring
        d = nrm(np.array((ox - cx, oy - cy, 0.0)))
        for (out_, dz) in rings:
            zz = top + dz * (top - bottom) / 0.036
            verts.append((ox + d[0] * out_, oy + d[1] * out_, zz))
    R_ = len(rings)
    for k in range(n):
        k2 = (k + 1) % n
        for r in range(R_ - 1):
            a, b = k * R_ + r, k2 * R_ + r
            faces.append([a, a + 1, b + 1, b]); uvs.append([(k / n, 1 - r / R_), (k / n, 1 - (r + 1) / R_), ((k + 1) / n, 1 - (r + 1) / R_), ((k + 1) / n, 1 - r / R_)])
        sharp += [(k * R_ + 1, k2 * R_ + 1), (k * R_ + 4, k2 * R_ + 4)]
    c = len(verts); verts.append((cx, cy, -0.002))
    for k in range(n):
        faces.append([k * R_ + R_ - 1, c, ((k + 1) % n) * R_ + R_ - 1]); uvs.append([(0.5, 0.05), (0.5, 0.0), (0.52, 0.05)])
    part.add(np.array(verts), faces, "Boots", uvs, {"sole": 1.0}, sharp)
    # tread lugs around the sole side wall (real geometry, read from the side) and under the forefoot/heel
    for k in range(0, n, 2):
        ox, oy = outline[k]
        d = nrm(np.array((ox - cx, oy - cy, 0.0)))
        r_, u_, n_ = gear.frame_from(d, (0, 0, 1))
        heel = ss(ymax - 0.09, ymax - 0.03, oy)
        rbox(part, np.array((ox, oy, 0.006 + 0.003 * heel)) + d * 0.004, r_, u_, n_, (0.011, 0.012, 0.005), 0.0015, 1, mat="Boots",
             attrs={"sole": 1.0})
