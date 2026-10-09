"""Cyberpunk street-survivor layers for the NPCs, built over their MakeHuman CC0 base clothes.

Oren  - patched parka with a rolled hood, scarf, respirator hanging on a strap, rugged cyber brace on the left forearm,
        fingerless gloves.
Mira  - oversized hoodie with LED drawstrings and hem trim, LED headset, satchel.
Tomas - respirator half-mask, goggles, scarf, LED trim on the robe, cybernetic right forearm and hand plating.
Maren - long lab coat with illuminated trim (echo hologram in game).
Nia   - small hoodie with LED trim (echo hologram in game).
Garments use Cloth_<Name> materials (baked BaseColor first in the manifest, so the current Unity builder already
shows them); hard parts use Gear / Strap / Metal / Glow / Glow2 / Lens / Scarf / Armor slots.
"""
import math
import numpy as np
import gear
from gear import Part, nrm, ss, shell, plate, pouch, buckle, strap, surface_path, light_strip, tube, rbox, bolt, limb_coords, fbm
from outfit_kael import limb_ring


def _hood_roll(ctx, part, mat, push=0.03, thick=0.025):
    """A bunched hood rolled at the back of the neck."""
    L = ctx.L
    nc = np.array((0, L["Neck"][1] + 0.02, L["Neck"][2] - 0.03))
    pts = []
    for k in range(15):
        a = math.pi * (0.25 + 1.5 * k / 14)
        d = np.array((math.sin(a), -math.cos(a), 0.0))
        hit, nn = ctx.cast(nc + d * 0.2, -d, 0.22)
        p = (hit + nn * push) if hit is not None else nc + d * 0.1
        pts.append(p + np.array((0, 0, 0.012 * math.sin(math.pi * k / 14))))
    rad = [thick * (0.6 + 0.4 * math.sin(math.pi * k / 14)) for k in range(15)]
    gear.tube(part, np.array(pts), np.array(rad), 10, mat=mat, caps=True)


def _respirator(ctx, part, center, fwd, up, scale=1.0):
    r, u, n = gear.frame_from(fwd, up)
    c = np.asarray(center)
    rbox(part, c, r, u, n, (0.07 * scale, 0.055 * scale, 0.03 * scale), 0.012 * scale, 2, mat="Gear", attrs={"plate": 1.0})
    for s_ in (1, -1):
        fc = c + r * s_ * 0.042 * scale - u * 0.012 * scale + n * 0.006 * scale
        tube(part, [fc - r * s_ * 0.004, fc + r * s_ * 0.018 * scale + n * 0.004], 0.017 * scale, 12, mat="Gear", caps=True)
        tube(part, [fc + r * s_ * 0.019 * scale + n * 0.004, fc + r * s_ * 0.0215 * scale + n * 0.005], 0.0175 * scale, 12, mat="Metal", caps=True)
    rbox(part, c + n * 0.016 * scale - u * 0.006 * scale, r, u, n, (0.024 * scale, 0.02 * scale, 0.008 * scale), 0.003, 1, mat="Metal")
    rbox(part, c + n * 0.0205 * scale - u * 0.006 * scale, r, u, n, (0.014 * scale, 0.004 * scale, 0.002), 0.001, 1, mat="Glow")


def _cyber_forearm(ctx, part, side, rust=False):
    bone = "LeftForeArm" if side > 0 else "RightForeArm"
    el = ctx.L[bone]; wr = ctx.L["LeftHand" if side > 0 else "RightHand"]
    ax = nrm(wr - el); flen = np.linalg.norm(wr - el)
    for si, (t0, t1) in enumerate(((0.1, 0.45), (0.5, 0.88))):
        tm = (t0 + t1) / 2
        c = el + (wr - el) * tm
        for ph, mt in ((math.radians(-10), "Metal"), (math.radians(-100), "Armor")):
            p, n = ctx.limb_point(bone, tm, ph, ref=(0, 0, 1), R=0.1)
            plate(ctx, part, p, n, ax, 0.026, (t1 - t0) * flen * 0.5, mode="radial", pivot=c, poly=[(-1, 1), (1, 1), (0.9, -1), (-0.9, -1)],
                  corner=0.2, offset=0.005, thickness=0.005, crown=0.002, chamfer=0.0025, mat_top=mt, mat_edge="Metal", mat_wall="Gear",
                  plate_id=10 + si, segs=24, cast_r=0.1, bolts=[(-0.75, 0.0), (0.75, 0.0)])
    pts = [ctx.limb_point(bone, t, math.radians(-55), push=0.0035, ref=(0, 0, 1), R=0.1) for t in np.linspace(0.08, 0.92, 12)]
    light_strip(part, np.array([p for p, _ in pts]), np.array([n for _, n in pts]), 0.0022, 0.001, mat="Glow")
    for t in (0.1, 0.92):
        ring = [ctx.limb_point(bone, t, 2 * math.pi * k / 18, push=0.005, ref=(0, 0, 1), R=0.1) for k in range(19)]
        strap(part, np.array([p for p, _ in ring]), np.array([n for _, n in ring]), 0.012, 0.004, mat="Metal", attrs={"wear": 1.0}, caps=False)


def build(ctx, cid):
    L, R = ctx.L, ctx.region
    co = ctx.basis
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    hips_z = L["Hips"][2]
    nm = ctx.name
    objs = {}
    # Base MakeHuman clothes form the surface we layer onto.
    for o in getattr(ctx, "base_clothes", []):
        ctx.push_stack(o)
    if cid == "oren":
        pm = (R["torso"] + R["uarmL"] + R["uarmR"] + R["farmL"] + R["farmR"] + R["hips"]) > 0.5
        pm &= (R["neck"] < 0.5) & (R["head"] < 0.02) & (R["handL"] < 0.3) & (R["handR"] < 0.3) & (z > hips_z - 0.16)
        tl, _, _ = limb_coords(co, L["LeftForeArm"], L["LeftHand"])
        pm &= ~((x > 0.2) & (tl > 0.02))   # left sleeve pushed up above the elbow (cyber brace)
        objs["Parka"] = shell(ctx, f"{nm}_Parka", pm, lambda P, N: np.full(len(P), 0.026) + 0.01 * ss(1.0, 1.3, P[:, 2]), mats=("Cloth_Parka",),
                              smooth=6, subdiv=0, rim=0.008, cover=False, bsmooth=14,
                              disp=lambda P, N: 0.004 * fbm(P, 9.0, 3, 1.0) + 0.003 * np.sin(P[:, 2] / 0.035 * 6.28 + 2 * fbm(P, 6, 2, 2.0)) * ss(1.2, 0.9, P[:, 2]))
        hd = Part(f"{nm}_Hood")
        _hood_roll(ctx, hd, "Cloth_Parka")
        objs["Parka"] = gear.join([objs["Parka"], hd.build()], f"{nm}_Parka")
        g = Part(f"{nm}_Gear")
        # respirator hanging on the chest from a neck strap
        hit, nn = ctx.cast(np.array((0.02, -0.5, L["Spine2"][2] + 0.11)), (0, 1, 0), 0.6)
        if hit is not None:
            _respirator(ctx, g, hit + nn * 0.03, nrm(nn + np.array((0, 0, -0.3))), (0, 0, 1))
            P_, N_ = surface_path(ctx, [hit + np.array((0.04, 0, 0.02)), np.array((0.07, -0.06, L["Neck"][2] - 0.02)), np.array((0, 0.06, L["Neck"][2])),
                                        np.array((-0.07, -0.06, L["Neck"][2] - 0.02)), hit + np.array((-0.04, 0, 0.02))], 30, push=0.004)
            strap(g, P_, N_, 0.012, 0.0025, mat="Strap")
        _cyber_forearm(ctx, g, 1, rust=True)
        objs["Gear"] = g.build()
        sc = Part(f"{nm}_ScarfLayer")
        nc = np.array((0, L["Neck"][1], L["Neck"][2] - 0.035))
        for k in range(3):
            pts = [nc + np.array((math.sin(a) * (0.085 + 0.006 * k), -math.cos(a) * (0.08 + 0.006 * k), 0.012 * k + 0.01 * math.sin(a * 3))) for a in np.linspace(0, 2 * math.pi, 25)]
            tube(sc, np.array(pts), 0.016, 8, mat="Scarf")
        objs["Scarf"] = sc.build()
        gl = (R["handL"] + R["handR"]) > 0.3
        dw = np.minimum(np.linalg.norm(co - L["LeftHand"], axis=1), np.linalg.norm(co - L["RightHand"], axis=1))
        objs["Gloves"] = shell(ctx, f"{nm}_Gloves", gl & (dw < 0.1), lambda P, N: np.full(len(P), 0.0025), mats=("Gloves",), smooth=1, subdiv=0, rim=0.003,
                               stack=False, cover=False)
    elif cid in ("mira", "nia"):
        hm = (R["torso"] + R["uarmL"] + R["uarmR"] + R["farmL"] + R["farmR"] + R["hips"]) > 0.5
        hm &= (R["neck"] < 0.5) & (R["head"] < 0.02) & (R["handL"] < 0.3) & (R["handR"] < 0.3) & (z > hips_z - 0.08)
        off = 0.022 if cid == "mira" else 0.018
        objs["Hoodie"] = shell(ctx, f"{nm}_Hoodie", hm, lambda P, N: np.full(len(P), off), mats=("Cloth_Hoodie",), smooth=6, subdiv=0, rim=0.007,
                               cover=True, bsmooth=14, disp=lambda P, N: 0.003 * fbm(P, 10.0, 3, 4.0))
        hd = Part(f"{nm}_Hood")
        _hood_roll(ctx, hd, "Cloth_Hoodie", push=0.03, thick=0.03)
        objs["Hoodie"] = gear.join([objs["Hoodie"], hd.build()], f"{nm}_Hoodie")
        g = Part(f"{nm}_Gear")
        # LED drawstrings and hem trim
        for s_ in (1, -1):
            a0 = np.array((s_ * 0.04, -0.2, L["Neck"][2] - 0.07))
            P_, N_ = surface_path(ctx, [a0, a0 + np.array((s_ * 0.004, 0, -0.06)), a0 + np.array((s_ * 0.01, 0, -0.13))], 10, push=0.004)
            tube(g, P_, 0.0018, 6, mat="Glow2", caps=True)
        hem_z = hips_z - 0.07
        ring = []
        for k in range(41):
            phi = 2 * math.pi * k / 40
            d = np.array((math.sin(phi), -math.cos(phi), 0))
            hit, nn = ctx.cast(np.array((0, L["Hips"][1], hem_z + 0.015)) + d * 0.3, -d, 0.32)
            ring.append((hit + nn * 0.002) if hit is not None else np.array((0, 0, hem_z)) + d * 0.15)
        P_ = np.array(ring); N_ = np.array([nrm(np.array((p[0], p[1] - L["Hips"][1], 0))) for p in P_])
        light_strip(g, P_, N_, 0.003, 0.0012, mat="Glow")
        objs["Gear"] = g.build()
    elif cid == "tomas":
        cm = (R["torso"] + R["uarmL"] + R["uarmR"] + R["farmL"] + R["farmR"] + R["hips"] + R["thighL"] + R["thighR"]) > 0.5
        cm &= (R["neck"] < 0.5) & (R["head"] < 0.02) & (R["handL"] < 0.3) & (R["handR"] < 0.3) & (z > hips_z - 0.2)
        cm &= ~((np.abs(x) < 0.05) & (y < L["Spine1"][1] - 0.02))  # open front
        tr_, _, _ = limb_coords(co, L["RightForeArm"], L["RightHand"])
        cm &= ~((x < -0.2) & (tr_ > -0.04))  # right sleeve pushed up (cyber arm)
        objs["Coat"] = shell(ctx, f"{nm}_Coat", cm, lambda P, N: np.full(len(P), 0.02) + 0.008 * ss(1.0, 0.85, P[:, 2]), mats=("Cloth_Coat",),
                             smooth=6, subdiv=0, rim=0.007, cover=False, bsmooth=14,
                             disp=lambda P, N: 0.003 * fbm(P, 9.0, 3, 6.0) + 0.0025 * np.sin(P[:, 2] / 0.05 * 6.28 + 2 * fbm(P, 5, 2, 7.0)) * ss(1.0, 0.8, P[:, 2]))
        hd = Part(f"{nm}_Hood")
        _hood_roll(ctx, hd, "Cloth_Coat", push=0.032, thick=0.028)
        objs["Coat"] = gear.join([objs["Coat"], hd.build()], f"{nm}_Coat")
        ctx.push_stack(objs["Coat"])
        g = Part(f"{nm}_Gear")
        em = (L["LeftEye"] + L["RightEye"]) * 0.5
        hit, nn = ctx.cast(np.array((0, -0.4, em[2] - 0.075)), (0, 1, 0), 0.5, ctx.tree)
        if hit is not None:
            _respirator(ctx, g, hit + nn * 0.024, nrm(nn + np.array((0, 0, -0.2))), (0, 0, 1), 0.95)
            for s_ in (1, -1):
                P_, N_ = surface_path(ctx, [hit + np.array((s_ * 0.035, 0.0, 0.0)), np.array((s_ * 0.075, em[1] + 0.03, em[2] - 0.045)),
                                            np.array((s_ * 0.07, em[1] + 0.1, em[2] - 0.02))], 12, push=0.003, tree=ctx.tree)
                strap(g, P_, N_, 0.012, 0.002, mat="Strap")
        _cyber_forearm(ctx, g, -1)
        # LED trim down the robe front edges
        for s_ in (1, -1):
            P_, N_ = surface_path(ctx, [np.array((s_ * 0.06, -0.3, L["Spine2"][2] + 0.1)), np.array((s_ * 0.09, -0.3, hips_z)), np.array((s_ * 0.1, -0.3, hips_z - 0.4))], 30, push=0.003)
            light_strip(g, P_, N_, 0.003, 0.0012, mat="Glow")
        objs["Gear"] = g.build()
    elif cid == "maren":
        cm = (R["torso"] + R["uarmL"] + R["uarmR"] + R["farmL"] + R["farmR"] + R["hips"]) > 0.5
        cm &= (R["neck"] < 0.5) & (R["head"] < 0.02) & (R["handL"] < 0.3) & (R["handR"] < 0.3) & (z > hips_z - 0.14)
        cm &= ~((np.abs(x) < 0.04) & (y < L["Spine1"][1] - 0.02))  # open front
        objs["LabCoat"] = shell(ctx, f"{nm}_LabCoat", cm, lambda P, N: np.full(len(P), 0.02), mats=("Cloth_LabCoat",), smooth=6, subdiv=0, rim=0.006,
                                cover=False, bsmooth=14)
        g = Part(f"{nm}_Gear")
        for s_ in (1, -1):
            P_, N_ = surface_path(ctx, [np.array((s_ * 0.045, -0.3, L["Spine2"][2] + 0.08)), np.array((s_ * 0.05, -0.3, hips_z)), np.array((s_ * 0.05, -0.3, hips_z - 0.13))], 26, push=0.002)
            light_strip(g, P_, N_, 0.0028, 0.0012, mat="Glow")
        objs["Gear"] = g.build()
    return objs
