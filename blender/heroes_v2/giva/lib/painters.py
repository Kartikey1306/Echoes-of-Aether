"""Giva's material painters (texture-space, procedural from 3D data). Every painter takes a raster.Maps and
returns linear float images (H,W,C); s7 writes them (BaseColor sRGB-encoded, data maps linear).

Design (STYLE.md): asymmetric graphite tech suit with violet accent panels, layered hard shells with painted
composite + anodised edges, nylon webbing, rubber, glowing conduits; value range kept readable under the dark
neon-night lighting (graphite and charcoal with lighter panels, metal edges that catch light)."""
import math
import numpy as np
import gv, raster, paint as pt

REG = {"torso": 0, "armL": 1, "armR": 2, "collar": 3, "cuff": 4, "legL": 5, "legR": 6}


# ============================================================================= suit (Garment_Top / Garment_Pants)

class SuitCoords:
    def __init__(self, F, maps):
        self.F = F
        m = maps.mask
        P = maps.P[m].astype(np.float64)
        self.P = P
        self.z, self.phi = F.torso(P)
        self.tA = {}
        for side in ("Left", "Right"):
            t, phi, r, L = F.chain(P, [side + "Arm", side + "ForeArm"], ref=(0, 0, 1.0))
            self.tA[side] = (t, phi, r, L)
            t2, phi2, r2, L2 = F.chain(P, [side + "UpLeg", side + "Leg"], ref=(1.0 if side == "Left" else -1.0, 0, 0))
            self.tA[side + "Leg"] = (t2, phi2, r2, L2)


COLLAR_MASK = [None]


def suit_design(maps, F, part, ao):
    """Returns (mask RGBA, height) for the garment atlas. part: 'top' or 'pants'. Layout from design.py (the same
    fields raised the panels as geometry in stage 3): violet bonded overlays with stitched, worn light edges, a raised
    graphite strap over the chest band, construction seams, technical knit, dark stretch gussets, light grime."""
    import design
    m = maps.mask
    S = maps.size
    C = SuitCoords(F, maps)
    P = C.P
    n = len(P)
    rg = maps.attr["rg"][m].round().astype(int) if "rg" in maps.attr else np.zeros(n, int)
    pnl = maps.attr["panel"][m].round().astype(int) if "panel" in maps.attr else np.zeros(n, int)
    accent = np.zeros(n)
    trim = np.zeros(n)
    dark = np.zeros(n)
    h = np.zeros(n)
    z, phi = C.z, C.phi
    r_t = design.R_T
    u_t = phi * r_t
    seam_d = np.full(n, 1e3)
    seam_s = np.zeros(n)

    def seam(d, s_, mask=None, w=0.0007, depth=0.00035, stitch=True):
        nonlocal seam_d, seam_s, h, dark
        d = np.abs(d)
        sel = np.ones(n, bool) if mask is None else mask
        dd = np.where(sel, d, 1e3)
        h += pt.groove(dd, w, depth)
        dark += 0.35 * np.exp(-(dd / (w * 1.6)) ** 2)
        if stitch:
            better = dd < seam_d
            seam_d = np.where(better, dd, seam_d)
            seam_s = np.where(better, s_, seam_s)

    f = design.fields(P, F, rg)
    vio, sash = f["violet"], f["sash"]
    # ---------------------------------------------------------------- bonded overlays (geometry raised in stage 3)
    accent = np.clip((vio + 0.0004) / 0.0008, 0, 1)
    along = np.where(np.isin(rg, (design.TORSO,)), z + u_t, 0.0)
    for side, key in (("Left", "armL"), ("Right", "armR")):
        sel = rg == REG[key]
        along = np.where(sel, C.tA[side][0], along)
    for side, key in (("Left", "legL"), ("Right", "legR")):
        sel = rg == REG[key]
        along = np.where(sel, C.tA[side + "Leg"][0], along)
    for fld, lift in ((vio, 1.0), (sash, 1.0)):
        inside = fld > 0
        # worn, lighter rim on the top edge of every overlay (catches light, reads at night)
        rim = np.exp(-(np.maximum(fld, 0) / 0.0016) ** 2) * inside
        trim += 0.32 * rim
        # double-needle stitching 2.5 mm inside the edge
        seam(fld - 0.0028, along, inside & (fld < 0.006), w=0.0004, depth=0.00015)
        # soft contact shadow on the base fabric right outside the overlay
        dark += 0.28 * np.exp(-(np.maximum(-fld, 0) / 0.0025) ** 2) * (~inside)
    trim += np.where(sash > 0, 0.16, 0.0)
    trim += 0.1 * accent                                       # satin bonded panels: a touch of sheen
    h += np.where(sash > 0, pt.periodic_ribs(along, 0.0055, 0.00025, 2), 0.0)
    dark += np.where(pnl == 2, 0.45, 0.0)                     # walls of the overlays
    # ---------------------------------------------------------------- torso
    tor = rg == REG["torso"]
    if part == "top":
        for ph0 in (math.pi / 2 + 0.05, -math.pi / 2 - 0.05):
            seam((phi - ph0) * r_t, z, tor)
        seam(u_t, z, tor & (z < 1.19) & (np.abs(phi) < 0.3))                          # centre front (abdomen)
        seam((np.abs(phi) - math.pi) * r_t, z, tor & (np.abs(phi) > 2.8))             # centre back
        yoke_z = 1.385 - 0.02 * np.cos(phi)
        seam(z - yoke_z, u_t, tor & (np.abs(phi) > 1.2))                              # shoulder yoke (sides/back)
        yk = tor & (z > yoke_z) & (np.abs(phi) > 1.2)
        trim += np.where(yk, 0.1, 0.0)
        h += np.where(yk & (phi > 0), pt.quilt(u_t, z, 0.022, 0.0007), 0.0)
        # under-bust band line (front), lumbar ribs (back), side stretch gussets
        seam(z - (1.168 + 0.01 * (1 - np.cos(phi)) / 2), u_t, tor & (np.abs(phi) < 1.3) & (vio < 0))
        lumbar = tor & (np.abs(phi) > 2.55) & (z > 1.0) & (z < 1.12)
        h += np.where(lumbar, pt.periodic_ribs(z, 0.006, 0.0005), 0.0)
        dark += np.where(lumbar & (accent < 0.5), 0.3, 0.0)
        seam(z - 1.12, u_t, tor & (np.abs(phi) > 2.55))
        gus = tor & (np.abs(np.abs(phi) - math.pi / 2) < 0.34) & (z > 1.03) & (z < 1.34)
        dark += np.where(gus & (accent < 0.5), 0.36, 0.0)
        h += np.where(gus, pt.periodic_ribs(z, 0.0045, 0.0004, 3), 0.0)
        # waist construction seam (Top/Pants split)
        seam(z - 0.9955, u_t, tor & (z < 1.01))
        # collar: graphite outside, violet inset at the front, piping on the top edge, ribbed
        col = rg == REG["collar"]
        neck = F.h["Neck"]
        if col.any():
            zc = z[col]
            ztop = np.percentile(zc, 97)
            pip = col & (z > ztop - 0.004)
            trim[pip] = 0.6
            h += np.where(col, pt.periodic_ribs(z, 0.0042, 0.0003, 2), 0.0) * (~pip)
            front = col & (np.abs(phi) < 0.2) & (~pip)
            accent[front] = 1
            seam((np.abs(phi) - 0.2) * 0.07, z, col & (~pip), w=0.0006)
            Nm = maps.N[m]
            inside_c = col & ((Nm[:, :2] * (P[:, :2] - neck[:2])).sum(1) < 0)
            dark[inside_c] += 0.2
            COLLAR_MASK[0] = col & ~inside_c
        # sleeves
        for side, key in (("Left", "armL"), ("Right", "armR")):
            a = rg == REG[key]
            t, ph, r, L = C.tA[side]
            arc = ph * design.R_ARM
            seam((np.abs(ph) - math.pi) * design.R_ARM, t, a & (vio < 0))
            seam(t - 0.025, arc, a)
            L1 = np.linalg.norm(F.t[side + "Arm"] - F.h[side + "Arm"])
            if side == "Left":
                # darker forearm sleeve (concept): from just below the elbow band
                fa = a & (t > L1 + 0.01)
                dark += np.where(fa, 0.42, 0.0)
                seam(t - (L1 + 0.01), arc, a)
                h += np.where(fa, pt.periodic_ribs(t, 0.008, 0.00035, 2), 0.0)
            else:
                seam(t - L1 * 0.55, arc, a & (vio < 0))
            inner = a & (np.abs(t - L1) < 0.06) & (np.abs(np.abs(ph) - 0.9) < 0.9)
            wr = pt.fbm(P, 60, 2, seed=3)
            h += np.where(inner, 0.0009 * np.sin((t - L1) / 0.011 * math.pi + wr * 3) * np.exp(-((t - L1) / 0.04) ** 2), 0.0)
            # wrist end: ribbed cuff band
            Lw = L1 + np.linalg.norm(F.t[side + "ForeArm"] - F.h[side + "ForeArm"]) * 0.93
            cb = a & (t > Lw - 0.03)
            h += np.where(cb, pt.periodic_ribs(arc, 0.003, 0.0003, 2), 0.0)
            seam(t - (Lw - 0.03), arc, a)
            dark += np.where(cb, 0.2, 0.0)
    else:
        for side, key in (("Left", "legL"), ("Right", "legR")):
            a = rg == REG[key]
            t, ph, r, L = C.tA[side + "Leg"]
            arc = ph * design.R_LEG
            seam((np.abs(ph) - math.pi) * design.R_LEG, t, a)
            seam(ph * design.R_LEG, t, a & (t > 0.06) & (vio < 0))
            L1 = np.linalg.norm(F.t[side + "UpLeg"] - F.h[side + "UpLeg"])
            inner = a & (np.abs(ph) > 2.3) & (t > 0.1)
            dark += np.where(inner, 0.3, 0.0)
            bk = a & (np.abs(t - L1) < 0.07) & (np.abs(np.abs(ph) - math.pi / 2) > 2.1 - math.pi / 2 + 0.6)
            wr = pt.fbm(P, 50, 2, seed=9)
            h += np.where(bk, 0.001 * np.sin((t - L1) / 0.012 * math.pi + wr * 3) * np.exp(-((t - L1) / 0.05) ** 2), 0.0)
            seam(t - 0.13, arc, a & (vio < 0))
            sh = a & (t > L1 + 0.04)
            h += np.where(sh, pt.periodic_ribs(t, 0.006, 0.0003, 2), 0.0)
        seam(P[:, 0], z, (np.abs(P[:, 0]) < 0.03) & (z > 0.8))
        back = P[:, 1] > 0.0
        seam(z - (0.9 + 0.06 * np.abs(P[:, 0]) / 0.15), P[:, 0], back & (z > 0.8))
        seam(z - 0.9955, P[:, 0], z > 0.98)
    # ---------------------------------------------------------------- common
    h += np.where(seam_d < 0.006, pt.stitches(seam_d, seam_s), 0.0)
    u2 = np.where(np.isin(rg, (REG["armL"], REG["armR"], REG["legL"], REG["legR"])), 0.0, u_t)
    v2 = z
    for side, keys in (("Left", (REG["armL"], REG["legL"])), ("Right", (REG["armR"], REG["legR"]))):
        for k_i, key in enumerate(keys):
            sel = rg == key
            t, ph, r, L = C.tA[side] if k_i == 0 else C.tA[side + "Leg"]
            u2 = np.where(sel, ph * (design.R_ARM if k_i == 0 else design.R_LEG), u2)
            v2 = np.where(sel, t, v2)
    h += pt.knit(u2, v2) * np.where(accent > 0.5, 0.45, 1.0)
    # light grime / wear (large soft blotches, more on the lower body), kept subtle
    g1 = pt.fbm(P * 1.0, 7, 3, seed=21)
    g2 = pt.fbm(P * 1.0, 31, 2, seed=22)
    grime = np.clip((g1 - 0.52) * 2.2, 0, 1) * (0.5 + 0.5 * g2) * (0.06 + 0.06 * np.clip((1.2 - z) / 0.6, 0, 1))
    dark += grime
    mask_img = np.zeros((S, S, 4), np.float32)
    A = np.clip((1 - ao[m]) * 1.1 + np.clip(dark, 0, 1), 0, 1)
    if COLLAR_MASK[0] is not None and len(COLLAR_MASK[0]) == len(A):
        # the mock collar reads as the same grey suit fabric (the chin/hair occlusion in the bake made it near-black)
        A = np.where(COLLAR_MASK[0], np.minimum(A, 0.28), A)
        COLLAR_MASK[0] = None
    mask_img[m] = np.stack([np.clip(accent, 0, 1), np.clip(trim, 0, 1), np.zeros(n), A], 1)
    H = np.zeros((S, S), np.float32)
    H[m] = h
    return mask_img, H


# ============================================================================= hard surface + gear

def wear_from_normal(nrm, mask, k=3):
    """Convexity (edges) and cavity from a tangent-space normal map (divergence)."""
    nx = nrm[..., 0] * 2 - 1
    ny = nrm[..., 1] * 2 - 1
    div = (np.roll(nx, -k, 1) - np.roll(nx, k, 1)) + (np.roll(ny, -k, 0) - np.roll(ny, k, 0))
    div = np.where(mask, div, 0)
    edge = np.clip(div * 4.0, 0, 1)
    cav = np.clip(-div * 4.0, 0, 1)
    return edge, cav


def paint_hard(maps, ao, nrm, cls_map, scheme):
    """Generic hard-surface/gear painter. scheme: {cls: dict(base=(r,g,b) linear, metal, smooth, wear, grime)}.
    Returns base (H,W,3 linear), maskmap (H,W,4), normal (H,W,3)."""
    S = maps.size
    m = maps.mask
    P = maps.P
    # wear from the curvature of a slightly blurred bake (single-texel seams between baked triangles must not read
    # as scratches); only real bevels and rims get worn edges
    nb = raster.blur(nrm, 2, m)
    edge, cav = wear_from_normal(nb, m)
    edge = np.clip((edge - 0.18) * 1.6, 0, 1)
    cav = np.clip((cav - 0.18) * 1.6, 0, 1)
    # plates: wear lives on the filleted rims only (the bake of a curved shell on a coarse cage has curvature
    # discontinuities at every low-poly edge that would otherwise read as a scratch network)
    if "plate" in maps.attr and "top" in maps.attr:
        pl = maps.attr["plate"] > 0.5
        rim = np.clip(1.0 - maps.attr["top"], 0, 1) ** 0.7
        edge = np.where(pl, rim, edge)
        cav = np.where(pl, 0.0, cav)
    noise = np.zeros((S, S), np.float32)
    noise[m] = pt.fbm(P[m].astype(np.float64), 180, 4, seed=5)
    big = np.zeros((S, S), np.float32)
    big[m] = pt.fbm(P[m].astype(np.float64), 25, 3, seed=11)
    base = np.zeros((S, S, 3), np.float32)
    mm = np.zeros((S, S, 4), np.float32)
    mm[..., 1] = 1
    for c, d in scheme.items():
        sel = m & (np.abs(cls_map - c) < 0.5)
        if not sel.any():
            continue
        b = np.array(d["base"], np.float32)
        col = np.broadcast_to(b, (S, S, 3)).copy()
        var = (big - 0.5) * d.get("var", 0.12) + (noise - 0.5) * d.get("fine", 0.06)
        col = col * (1 + var[..., None])
        wear = np.clip(edge * d.get("wear", 0.6) * (0.6 + 0.8 * noise), 0, 1)
        if d.get("wear_col") is not None:
            col = col * (1 - wear[..., None]) + np.array(d["wear_col"], np.float32) * wear[..., None]
        grime = np.clip((1 - ao) * d.get("grime", 0.5) + cav * 0.3, 0, 1)
        col = col * (1 - grime[..., None] * 0.55)
        base[sel] = col[sel]
        metal = d.get("metal", 0.0) * (1 - wear) + d.get("wear_metal", 0.0) * wear
        smooth = d.get("smooth", 0.5) * (1 - grime * 0.35) + wear * d.get("wear_smooth", 0.1) + (noise - 0.5) * 0.08
        mm[sel, 0] = np.clip(metal, 0, 1)[sel]
        mm[sel, 1] = np.clip(ao, 0, 1)[sel]
        mm[sel, 2] = d.get("paint", 0.0)
        mm[sel, 3] = np.clip(smooth, 0, 1)[sel]
    return base, mm


def decal(P, mask, c, n, up, kind, size, text=""):
    """Decal coverage (0..1) at texels P: 'chev' hazard chevrons, 'text' glyph serial, 'ring' target ring."""
    x, y, dep = pt.local2(P, np.asarray(c, float), np.asarray(n, float), np.asarray(up, float))
    near = mask & (np.abs(dep) < 0.03)
    out = np.zeros(P.shape[:-1], np.float32)
    if kind == "chev":
        cov = pt.chevrons(x, y, size[1] / 2, size[1] * 1.6) * (np.abs(x) < size[0] / 2)
        out = np.where(near, cov, 0)
    elif kind == "text":
        d = pt.text_sdf(x + size[0] / 2, y + size[1] / 2, text, size[1])
        out = np.where(near, np.clip(1 - d / (size[1] * 0.09), 0, 1), 0)
    elif kind == "stripe":
        out = np.where(near & (np.abs(x) < size[0] / 2) & (np.abs(y) < size[1] / 2), 1.0, 0.0)
    return out.astype(np.float32)
