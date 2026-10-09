"""Giva suit layout (master concept, dreamlayer/characters/lyra/giva_master_front.png): one definition of every
colour-blocked panel as a signed distance field (metres, > 0 inside), shared by the geometry (stage 3 raises the
panels as real bonded overlays) and the texture painter (accent mask, edge seams and wear).

Coordinates: torso (z, u = phi * R_T, phi = 0 front, + character left); limbs: arc length t from the chain head
and phi around it (arms: 0 = up, legs: 0 = lateral).
"""
import math
import numpy as np

R_T = 0.135          # torso arc radius used for u
R_ARM = 0.045
R_LEG = 0.065

# region ids (same numbering as painters.REG)
TORSO, ARM_L, ARM_R, COLLAR, CUFF, LEG_L, LEG_R = 0, 1, 2, 3, 4, 5, 6

# violet chest band: her right shoulder -> under the Aether core on the upper left chest
CHEST_A = np.array((-0.168, 1.428))
CHEST_B = np.array((0.082, 1.300))
CHEST_W = 0.033
# raised graphite strap along the band's upper edge
SASH_OFF = 0.045
SASH_W = 0.0095
# angled waist / hip panels (cross the Top/Pants split)
WAIST_R = (np.array((-0.083, 1.135)), np.array((-0.128, 0.885)), 0.021)
WAIST_L = (np.array((0.072, 1.142)), np.array((0.132, 0.885)), 0.027)
# upper back V
BACK = ((0.300, 1.425), (0.402, 1.250), 0.022)
# Aether core (torso chart u, z) and housing radius: panels end under it
CORE = np.array((0.080, 1.335))


def seg_sd(p, a, b, w):
    """w - distance to segment ab (p: (N,2))."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    f = a + t[:, None] * ab
    return w - np.linalg.norm(p - f, axis=1)


def capsule_flat(p, a, b, w):
    """Band of half-width w along ab with square ends (signed)."""
    ab = b - a
    L = np.linalg.norm(ab)
    d = ab / L
    n = np.array((-d[1], d[0]))
    q = p - a
    along = q @ d
    across = q @ n
    return np.minimum.reduce([w - np.abs(across), along, L - along])


def torso_fields(z, phi):
    u = phi * R_T
    p = np.stack([u, z], 1)
    front = np.abs(phi) < 1.45
    f = {}
    # chest band, ending in a rounded cap under the core
    v = seg_sd(p, CHEST_A, CHEST_B, CHEST_W)
    v = np.where(front & (phi > -1.32), v, -1.0)
    # waist / hip panels
    for a, b, w in (WAIST_R, WAIST_L):
        v = np.maximum(v, np.where(np.abs(phi) < 1.6, capsule_flat(p, a, b, w), -1.0))
    # back V (both sides)
    for sg in (1, -1):
        a = np.array((sg * BACK[0][0], BACK[0][1]))
        b = np.array((sg * BACK[1][0], BACK[1][1]))
        v = np.maximum(v, np.where(np.abs(phi) > 1.9, seg_sd(p, a, b, BACK[2]), -1.0))
    f["violet"] = v
    d = (CHEST_B - CHEST_A) / np.linalg.norm(CHEST_B - CHEST_A)
    n = np.array((-d[1], d[0]))
    if n[1] < 0:
        n = -n
    sa = CHEST_A + n * SASH_OFF + d * 0.012
    sb = CHEST_B + n * SASH_OFF - d * 0.03
    s = capsule_flat(p, sa, sb, SASH_W)
    f["sash"] = np.where(front & (phi > -1.4), s, -1.0)
    return f


def arm_fields(side, t, ph, L1, L):
    """L1 upper-arm length, L arm chain length to the wrist."""
    f = {}
    if side == "Right":
        # front/inner face of the upper arm (rest pose: front of the right arm is phi = -pi/2)
        v = np.minimum.reduce([(0.95 - np.abs(ph + 1.75)) * R_ARM, t - 0.075, (L1 - 0.012) - t])
    else:
        c = L1 - 0.052
        v = np.minimum(0.017 - np.abs(t - c), np.full_like(t, 1.0))
        # outer forearm panel (concept): from below the elbow to the wrist band
        fa = np.minimum.reduce([(0.55 - np.abs(ph - 0.35)) * R_ARM, t - (L1 + 0.04), (L - 0.045) - t])
        v = np.maximum(v, fa)
    f["violet"] = v
    f["sash"] = np.full_like(t, -1.0)
    return f


LEG_C = 0.62          # left thigh panel centre angle (0 = lateral, + = front)


def leg_half(t, L1):
    return 0.58 - 0.16 * np.clip((t - 0.08) / (L1 - 0.1), 0, 1)


def leg_fields(side, t, ph, L1):
    f = {}
    if side == "Left":
        half = leg_half(t, L1)
        v = np.minimum.reduce([(half - np.abs(ph - LEG_C)) * R_LEG, t - 0.07, (L1 - 0.055) - t])
    else:
        v = np.full_like(t, -1.0)
    f["violet"] = v
    f["sash"] = np.full_like(t, -1.0)
    return f


def fields(X, F, region):
    """Signed fields for points X (N,3) with region ids (per point)."""
    n = len(X)
    out = {"violet": np.full(n, -1.0), "sash": np.full(n, -1.0)}
    z, phi = F.torso(X)
    tor = torso_fields(z, phi)
    for side, rid in (("Left", ARM_L), ("Right", ARM_R)):
        sel = region == rid
        if sel.any():
            t, ph, r, L = F.chain(X[sel], [side + "Arm", side + "ForeArm"], ref=(0, 0, 1.0))
            L1 = float(np.linalg.norm(F.t[side + "Arm"] - F.h[side + "Arm"]))
            Lw = L1 + float(np.linalg.norm(F.t[side + "ForeArm"] - F.h[side + "ForeArm"])) * 0.93
            a = arm_fields(side, t, ph, L1, Lw)
            for k in out:
                out[k][sel] = a[k]
    for side, rid in (("Left", LEG_L), ("Right", LEG_R)):
        sel = region == rid
        if sel.any():
            t, ph, r, L = F.chain(X[sel], [side + "UpLeg", side + "Leg"], ref=(1.0 if side == "Left" else -1.0, 0, 0))
            L1 = float(np.linalg.norm(F.t[side + "UpLeg"] - F.h[side + "UpLeg"]))
            a = leg_fields(side, t, ph, L1)
            for k in out:
                out[k][sel] = a[k]
    # torso-defined panels also run onto the hips of the pants (z > 0.86)
    # ... and onto the top of the shoulders (the chest band runs over her right deltoid without a seam at the
    # torso/arm region boundary, which made its edge zig-zag there)
    torso_like = (region == TORSO) | (((region == LEG_L) | (region == LEG_R)) & (z > 0.86)) | \
        (((region == ARM_L) | (region == ARM_R)) & (z > 1.3))
    for k in out:
        out[k] = np.where(torso_like, np.maximum(out[k], tor[k]), out[k])
    return out
