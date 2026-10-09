"""Hair style recipes for the customiser (KAEL: 20 men's styles from the user's chart, GIVA/lyra: 14 women's styles).

Angles: az 0 = front (-Y), + = character's left (+X), 180 = back; el = elevation from the head centre. All lengths in
metres along the lock. Each recipe configures a hair_build.HB builder.
"""
import math
import numpy as np
from common import ss, nrm, nrm_rows
from hairlib import (flow_forward, flow_back, flow_down, flow_from, flow_to, flow_part, blend_flows, braid3, fishtail,
                     bun as bun_geo, grow, resample, dirv, arclen, tangents)

R_ = np.radians
D_ = math.degrees


def knots(az, pairs):
    a, v = zip(*pairs)
    return np.interp(np.degrees(np.abs(az)), a, v)


def fade_fn(lo_pairs, hi_pairs, base=0.0):
    """Density 0..1 between elevation lo(az) and hi(az) (degrees), `base` below lo (0 = skin)."""
    def f(az, el, P):
        lo = R_(knots(az, lo_pairs)); hi = R_(knots(az, hi_pairs))
        return base + (1 - base) * ss(lo, hi, el)
    return f


def line_dist2(px, py, pts):
    d = np.full(len(px), 1e9)
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy + 1e-12
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
        d = np.minimum(d, np.hypot(px - ax - t * dx, py - ay - t * dy))
    return d


def side_design(H, lines, width=0.0013, xmin=0.035, sides=(1, -1)):
    """Shaved line design on the side(s) of the head; lines: list of polylines [(y, z), ...] relative to the head
    centre (metres; y + = back)."""
    def f(az, el, P):
        out = np.zeros(len(P))
        for sg in sides:
            m = (P[:, 0] * sg) > xmin
            if not m.any():
                continue
            y = P[m, 1] - H.hc[1]; z = P[m, 2] - H.hc[2]
            d = np.full(m.sum(), 1e9)
            for pts in lines:
                d = np.minimum(d, line_dist2(y, z, pts))
            out[m] = np.where(d < width * 0.5, 1.0, np.where(d < width * 0.5 + 0.0007, 0.35, 0.0))
        return out
    return f


def part_line(H, x0, width=0.0009, el_min=22.0, back=0.04):
    def f(az, el, P):
        d = np.abs(P[:, 0] - x0)
        m = (P[:, 1] < H.hc[1] + back) & (el > R_(el_min))
        return np.where(m & (d < width * 0.5), 1.0, np.where(m & (d < width * 0.5 + 0.0008), 0.35, 0.0))
    return f


def zone(az_rng=None, el_rng=None, absaz=True):
    def f(az, el, P):
        m = np.ones(len(az), bool)
        a = np.degrees(np.abs(az) if absaz else az)
        if az_rng:
            m &= (a >= az_rng[0]) & (a <= az_rng[1])
        if el_rng:
            e = np.degrees(el)
            m &= (e >= el_rng[0]) & (e <= el_rng[1])
        return m
    return f


def crown_pt(H, az=178, el=56):
    return H.surf(np.array(R_(az)), np.array(R_(el)))


def front_back_flow(H, front, back, a0=80, a1=135):
    def fl(P):
        az, el, r = H.angles(P)
        wf = 1 - ss(R_(a0), R_(a1), np.abs(az))
        return blend_flows(H, P, (wf, front(P)), (1 - wf, back(P)))
    return fl


def sweep_curve(side_fn, k=0.35, start=0.2, down=0.0):
    """Extra steering per step: sideways (sign from the root x) growing along the lock."""
    def make(p0):
        sg = side_fn(p0)
        def c(s, p, d):
            return np.array((sg * k * ss(start, 1.0, s), 0.0, -down * s))
        return c
    return make


# ============================================================================= shared building blocks


def long_layers(b, L, flow, tiles=(0, 15), wave=None, curl=None, ringlet_w=0.65, guard=None, rise=0.008, n_scale=1.0,
                frame_short=0.72, cutf=None, lift=0.1, grav=0.75, hug=0.9, width=(0.026, 0.013), flick=0.0, ramp=(0.1, 0.45),
                where=None, extra_layer=True, min_d=0.009):
    """Long hair in four offset layers (inner to outer) with shorter face-framing layers."""
    H = b.H
    layers = [(150, (0.003, 0.006), -40, 1.0), (170, (0.007, 0.011), -25, 1.0), (115, (0.012, 0.016), 0, 0.95)]
    if extra_layer:
        layers.append((55, (0.016, 0.021), 25, 0.86))
    for n, off, el_min, lm in layers:
        def length(a, e, p, lm=lm):
            Lx = (L(a, e, p) if callable(L) else L) * lm
            if p[1] < H.eye[1] + 0.035 and abs(p[0]) > 0.025 and D_(e) < 28:
                Lx *= frame_short
            return Lx
        w = (lambda az, el, P, m=el_min: (el > R_(m)) & (where(az, el, P) if where else True))
        b.locks_(int(n * n_scale), w, length, flow=flow, segs=24, lift=lift, stiff=1.0, grav=grav, off=off, hug=hug, rise=rise,
                 width=width, tiles=tiles, wave=wave, curl=curl, ringlet_w=ringlet_w, guard=guard, min_d=min_d, body_clear=0.008,
                 cutf=cutf, flick=flick, ramp=ramp)


def back_path(H, A, L, x=0.0, clear=0.022, n=26):
    """Path from A straight down the back of the neck / upper back, `clear` off the body + outfit."""
    from mathutils import Vector
    pts = [np.asarray(A, float)]
    for z in np.linspace(A[2] - 0.015, A[2] - L, n):
        hit, nn, _, d = H.outer.ray_cast(Vector((x, 0.6, z)), Vector((0, -1.0, 0)), 1.2)
        y = (hit.y + clear) if hit is not None else pts[-1][1]
        pts.append(np.array((x, y, z)))
    P = np.array(pts)
    for _ in range(4):
        P[1:-1, 1] = np.maximum(P[1:-1, 1], P[1:-1, 1] * 0.5 + (P[:-2, 1] + P[2:, 1]) * 0.25)
    return P


def scalp_path(H, ctrl, n, h):
    """Smooth path over the scalp through control (az, el) degrees, `h` metres above the scalp."""
    D = [dirv(R_(a), R_(e)) for a, e in ctrl]
    pts = []
    for d0, d1 in zip(D[:-1], D[1:]):
        om = math.acos(np.clip(np.dot(d0, d1), -1, 1))
        for t in np.linspace(0, 1, max(4, n // (len(D) - 1)), endpoint=False):
            if om < 1e-6:
                pts.append(d0)
            else:
                pts.append((math.sin((1 - t) * om) * d0 + math.sin(t * om) * d1) / math.sin(om))
    pts.append(D[-1])
    pts = np.array(pts)
    for _ in range(3):
        pts[1:-1] = pts[1:-1] * 0.5 + (pts[:-2] + pts[2:]) * 0.25
    pts = nrm_rows(pts)
    az = np.arctan2(pts[:, 0], -pts[:, 1]); el = np.arcsin(np.clip(pts[:, 2], -1, 1))
    return H.surf(az, el, h)


# ============================================================================= KAEL


def k_curly_medium(b):
    H = b.H
    b.nap = False
    b.vol_tex = "curly"
    b.vol_thick = lambda az, el: 0.004 + 0.012 * ss(R_(5), R_(40), el)
    b.fade = lambda az, el, P: 0.55 + 0.45 * ss(H.hairline_el(az, "male") + R_(3), H.hairline_el(az, "male") + R_(16), el)
    crown = crown_pt(H, 170, 62)
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_from(H, P, crown)), (0.6, flow_forward(H, P, 0.6)))
    b.tiles = ["curly"] * 16 + ["coily"] * 8

    def length(a, e, p):
        a = abs(D_(a)); e = D_(e)
        L = 0.15 if e > 32 else (0.12 if a > 120 else 0.085)
        if a < 45 and e > 16:
            L = 0.11
        if a > 140 and e < 0:
            L = 0.05
        return L
    gb = b.guard_brow(0.03, 0.01)
    b.locks_(300, lambda az, el, P: el > R_(12), length, segs=30, lift=0.4, stiff=1.0, grav=0.22, off=(0.006, 0.022), hug=0.5,
             rise=0.012, curl=(0.0068, 0.024), ringlet_w=0.6, tiles=(0, 15), min_d=0.0068, guard=gb)
    b.locks_(150, lambda az, el, P: el <= R_(14), lambda a, e, p: 0.05 if abs(D_(a)) < 150 else 0.04, segs=16, lift=0.3,
             stiff=1.0, grav=0.25, off=(0.004, 0.009), hug=0.6, curl=(0.005, 0.018), ringlet_w=0.6, tiles=(16, 23), min_d=0.0065)


def k_textured_fringe(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.0025 + 0.007 * ss(R_(10), R_(35), el)
    b.fade = fade_fn([(0, -90), (45, -90), (70, -2), (180, -18)], [(0, -80), (45, -80), (70, 14), (180, 2)])
    crown = crown_pt(H, 180, 55)
    b.flow = front_back_flow(H, lambda P: flow_forward(H, P, 0.3, spread=1.2), lambda P: flow_from(H, P, crown, 0.02), 95, 140)
    b.tiles = ["spiky"] * 8 + ["messy"] * 8 + ["straight"] * 8
    gb = b.guard_brow(0.028, 0.008)
    top = lambda az, el, P: (el > R_(16)) | ((np.abs(az) < R_(45)) & (el > R_(5)))
    b.locks_(360, top, lambda a, e, p: 0.07 - 0.03 * ss(60, 150, abs(D_(a))), segs=14, lift=0.22, stiff=1.15, grav=0.1,
             off=(0.003, 0.014), hug=0.8, rise=0.008, width=(0.012, 0.004), tiles=(0, 15), clump_=0.55, guard=gb, min_d=0.006,
             flick=0.003, lift_fn=lambda a, e, p: 0.3 if abs(a) < R_(70) else 0.08)
    b.locks_(160, lambda az, el, P: (el > R_(4)) & (el <= R_(18)) & (np.abs(az) > R_(40)), 0.025, segs=8, lift=0.15, stiff=1.0,
             grav=0.2, off=(0.002, 0.004), hug=0.8, width=(0.01, 0.005), tiles=(16, 23), min_d=0.007)


def k_korean_perm(b):
    H = b.H
    b.nap = False
    b.vol_thick = lambda az, el: 0.006 + 0.012 * ss(R_(5), R_(40), el)
    b.vol_tex = "curly"
    crown = crown_pt(H, 178, 60)
    b.flow = front_back_flow(H, lambda P: flow_forward(H, P, 0.55, spread=0.6), lambda P: flow_from(H, P, crown, 0.04), 75, 130)
    b.tiles = ["wavy"] * 8 + ["curly"] * 8 + ["wavy"] * 8
    gb = b.guard_brow(0.006, 0.006)

    def length(a, e, p):
        a = abs(D_(a)); e = D_(e)
        if a < 55:
            return 0.115
        if a > 130 and e < 5:
            return 0.06
        return 0.095 if e > 20 else 0.065
    b.locks_(260, lambda az, el, P: el > R_(14), length, segs=22, lift=0.3, stiff=1.0, grav=0.3, off=(0.006, 0.02), hug=0.55, rise=0.018,
             width=(0.016, 0.008), curl=(0.0065, 0.03), ringlet_w=0.62, tiles=(0, 15), guard=gb, min_d=0.0075)
    b.locks_(170, lambda az, el, P: el > R_(18), length, segs=20, lift=0.25, stiff=1.0, grav=0.3, off=(0.01, 0.024), hug=0.5, rise=0.02,
             width=(0.016, 0.007), wave=(0.007, 0.045), tiles=(0, 7), guard=gb, min_d=0.009, clump_=0.25)
    b.locks_(150, lambda az, el, P: el <= R_(16), lambda a, e, p: 0.05, segs=12, lift=0.15, stiff=1.0, grav=0.35, off=(0.004, 0.009),
             hug=0.7, width=(0.014, 0.007), wave=(0.004, 0.035), tiles=(16, 23), min_d=0.0075)


def k_mullet_fade(b):
    H = b.H
    b.kind = "skinned"
    b.vol_thick = lambda az, el: 0.003 + 0.008 * ss(R_(12), R_(40), el)
    # burst fade around the ears, full hair at the back (mullet)
    b.fade = lambda az, el, P: np.clip(1 - (1 - fade_fn([(0, -90), (45, -90), (70, -4), (125, -6), (150, -90), (180, -90)],
                                                          [(0, -80), (45, -80), (70, 15), (125, 12), (150, -80), (180, -80)])(az, el, P)), 0, 1)
    crown = crown_pt(H, 180, 50)
    b.flow = front_back_flow(H, lambda P: flow_forward(H, P, 0.15, spread=1.0), lambda P: flow_from(H, P, crown, 0.05), 85, 130)
    b.tiles = ["messy"] * 8 + ["spiky"] * 4 + ["wavy"] * 4 + ["wavy"] * 8
    gb = b.guard_brow(0.03, 0.01)
    b.locks_(260, lambda az, el, P: ((el > R_(16)) | (np.abs(az) < R_(50))) & (np.abs(az) < R_(140)), lambda a, e, p: 0.065,
             segs=12, lift=0.35, stiff=1.2, grav=0.1, off=(0.003, 0.013), hug=0.6, rise=0.012, width=(0.012, 0.004), tiles=(0, 11),
             clump_=0.5, guard=gb, min_d=0.0065, frizz=0.0006)
    b.sheets(lambda a: 0.17, part_x=None, wave=(0.008, 0.065), grav=0.6, hug=0.8, rise=0.006, layers=((0.004, (16, 19)), (0.009, (20, 23))),
             segs=18, flick=0.01, az_min=124, crown_el=34, body_clear=0.009)
    back = lambda az, el, P: (np.abs(az) >= R_(122)) & (el < R_(40))
    b.locks_(240, back, lambda a, e, p: 0.17 - 0.05 * ss(-30, 30, D_(e)), segs=20, lift=0.12, stiff=1.0, grav=0.6, off=(0.004, 0.016),
             hug=0.7, rise=0.006, width=(0.016, 0.006), wave=(0.009, 0.065), flick=0.012, tiles=(12, 23), min_d=0.0065, body_clear=0.008,
             clump_=0.3)


def k_curtain_bangs(b):
    H = b.H
    b.nap = False
    b.vol_thick = lambda az, el: 0.005 + 0.008 * ss(R_(5), R_(40), el)
    b.partline = part_line(H, 0.0, el_min=24)
    b.flow = lambda P: flow_part(H, P, 0.0, front=-0.2, down=0.7)
    b.tiles = ["straight"] * 8 + ["wavy"] * 8 + ["wisp"] * 8
    gf = b.guard_face(0.006)
    sweep = lambda p: 1.0 if p[0] >= 0 else -1.0
    # bangs: forward from the part, then swept out to the temples / cheekbones
    side_k = lambda s_, p, d: np.array((math.copysign(0.9, p[0] if abs(p[0]) > 1e-4 else 1.0) * ss(0.15, 0.7, s_), 0.0, 0.0))
    gbb = b.guard_brow(0.016, 0.006, sides=0.02)
    for n, off in ((90, (0.004, 0.009)), (70, (0.009, 0.014))):
        b.locks_(n, lambda az, el, P: (np.abs(az) < R_(50)) & (el > R_(20)), 0.12, flow=lambda P: flow_down(H, P),
                 segs=22, lift=0.0, stiff=0.8, grav=0.6, off=off, hug=1.6, rise=0.002, width=(0.014, 0.006), tiles=(0, 15),
                 guard=gbb, min_d=0.007, wave=(0.003, 0.06), curve=side_k)
    b.locks_(260, lambda az, el, P: np.abs(az) >= R_(40), lambda a, e, p: 0.12 if abs(D_(a)) < 140 else 0.1, segs=18, lift=0.15, stiff=1.0,
             grav=0.45, off=(0.004, 0.017), hug=0.75, rise=0.01, width=(0.016, 0.007), tiles=(0, 15), wave=(0.005, 0.06), guard=gf,
             min_d=0.0075, flick=0.004)


def k_two_block(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.0025 + 0.008 * ss(R_(16), R_(40), el)
    b.fade = fade_fn([(0, -90), (40, -90), (60, 10), (180, 8)], [(0, -80), (40, -80), (60, 16), (180, 14)], base=0.8)
    crown = crown_pt(H, 180, 58)
    b.flow = front_back_flow(H, lambda P: blend_flows(H, P, (1.0, flow_forward(H, P, 0.45)), (0.35, flow_part(H, P, 0.035, 0, 0.0))),
                             lambda P: flow_from(H, P, crown, 0.08), 70, 130)
    b.tiles = ["straight"] * 16 + ["straight"] * 8
    gb = b.guard_brow(0.012, 0.007)
    top = lambda az, el, P: (el > R_(20)) | ((np.abs(az) < R_(50)) & (el > R_(10)))
    b.locks_(380, top, lambda a, e, p: 0.11 if abs(D_(a)) < 120 else 0.08, segs=18, lift=0.2, stiff=1.0, grav=0.38, off=(0.004, 0.018),
             hug=0.6, rise=0.012, width=(0.014, 0.006), tiles=(0, 15), guard=gb, min_d=0.0065, clump_=0.25)


def k_textured_crop_design(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.002 + 0.006 * ss(R_(22), R_(42), el)
    b.fade = fade_fn([(0, -90), (40, -90), (60, -6), (180, -20)], [(0, -80), (40, -80), (60, 13), (180, 2)])
    b.design = side_design(H, [[(-0.055, 0.025), (-0.02, 0.031), (0.02, 0.029), (0.06, 0.016)],
                               [(0.015, 0.03), (0.035, 0.012), (0.07, 0.004)]], width=0.0016)
    b.flow = lambda P: flow_forward(H, P, 0.35, spread=0.8)
    b.tiles = ["spiky"] * 8 + ["messy"] * 8 + ["straight"] * 8
    gb = b.guard_brow(0.038, 0.004)
    top = lambda az, el, P: (el > R_(30)) | ((np.abs(az) < R_(45)) & (el > R_(10)))
    b.locks_(420, top, lambda a, e, p: 0.042, segs=10, lift=0.3, stiff=1.2, grav=0.08, off=(0.003, 0.01), hug=0.7, rise=0.008,
             width=(0.011, 0.004), tiles=(0, 15), guard=gb, clump_=0.5, min_d=0.0055, frizz=0.0004)


def k_flowing_waves(b):
    H = b.H
    b.kind = "skinned"
    b.vol_thick = lambda az, el: 0.006 + 0.008 * ss(R_(5), R_(40), el)
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_back(H, P, 0.25)), (0.4, flow_part(H, P, 0.03, front=0.2, down=0.3)))
    b.partline = part_line(H, 0.03, el_min=34, back=-0.01)
    b.tiles = ["wavy"] * 16 + ["wisp"] * 8
    gf = b.guard_face(0.012)
    b.nap = False
    b.tiles = ["sheetwave"] * 12 + ["wavy"] * 4 + ["wisp"] * 8
    b.sheets(lambda a: 0.17 + 0.05 * ss(60, 150, a), part_x=0.03, wave=(0.011, 0.075), grav=0.55, hug=0.8, rise=0.01, guard=gf,
             layers=((0.004, (0, 5)), (0.009, (6, 11)), (0.014, (4, 11))), segs=20, flick=0.006, az_min=30)
    long_layers(b, lambda a, e, p: 0.2 if abs(D_(a)) > 60 else 0.17, None, tiles=(8, 15), wave=(0.013, 0.075), guard=gf, rise=0.016,
                lift=0.22, grav=0.5, hug=0.7, width=(0.02, 0.009), frame_short=0.95, flick=0.006, n_scale=0.45, min_d=0.008)


def k_modern_bowl(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.004 + 0.01 * ss(R_(5), R_(40), el)
    b.fade = fade_fn([(0, -90), (45, -90), (70, -8), (180, -25)], [(0, -80), (45, -80), (70, 6), (180, -6)], base=0.25)
    crown = crown_pt(H, 175, 72)
    b.flow = lambda P: flow_from(H, P, crown, 0.15)
    b.tiles = ["straight"] * 8 + ["messy"] * 8 + ["straight"] * 8
    ph = b.rng.uniform(0, 6.28)

    def below(P):
        az, el, r = H.angles(P)
        a = np.degrees(np.abs(az))
        z = np.interp(a, [0, 40, 75, 110, 150, 180], [H.brow_z + 0.012, H.brow_z + 0.012, H.eye[2] + 0.008, H.eye[2] - 0.005, H.eye[2] - 0.02, H.eye[2] - 0.025])
        z = z + 0.004 * np.sin(P[:, 0] * 900 + ph) + 0.003 * np.sin(P[:, 1] * 1300 + ph)
        return P[:, 2] < z
    b.locks_(460, lambda az, el, P: el > R_(8), 0.13, segs=18, lift=0.18, stiff=1.0, grav=0.35, off=(0.004, 0.018), hug=0.7, rise=0.012,
             width=(0.014, 0.006), tiles=(0, 15), cutf=below, min_d=0.0062, clump_=0.25)


def k_man_bun_fade(b):
    H = b.H
    b.nap = False
    A = b.anchor(180, 36, 0.006)
    b.fade = fade_fn([(0, -90), (45, -90), (65, 2), (140, -2), (165, -90), (180, -90)], [(0, -80), (45, -80), (65, 18), (140, 14), (165, -80), (180, -80)])
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.0025)
    b.flow = lambda P: flow_to(H, P, A)
    b.tiles = ["sleek"] * 12 + ["braid"] * 4 + ["wavy"] * 8
    region = lambda az, el, P: (el > R_(20)) | (np.abs(az) < R_(55)) | ((np.abs(az) > R_(150)) & (el > R_(0)))
    b.gather(380, region, A, off=(0.0025, 0.007), width=(0.016, 0.012), tiles=(0, 11), min_d=0.0068)
    # three Dutch braids from the front hairline back to the bun
    for k, az0 in enumerate((-26, 0, 26)):
        path = scalp_path(H, [(az0, 34), (az0 * 0.8, 60), (az0 * 0.4, 84), (180 + az0 * 0.25 if az0 >= 0 else -180 + az0 * 0.25, 52),
                              (180 + az0 * 0.15 if az0 >= 0 else -180 + az0 * 0.15, 40)], 60, 0.0045)
        braid3(H, b.part, path, 0.0135, 12 + k, 1.0, b.rng, flat=0.5, taper=0.2)
    nA = H.radial(A[None])[0]
    bun_geo(H, b.part, A + nA * 0.022, nA * 0.8 + np.array((0, 0.2, 0.3)), 0.026, (16, 23), 1.0, b.rng, cards=80, messy=0.15)


def k_wolf_cut(b):
    H = b.H
    b.kind = "skinned"
    b.vol_thick = lambda az, el: 0.006 + 0.012 * ss(R_(10), R_(45), el)
    crown = crown_pt(H, 180, 60)
    b.flow = front_back_flow(H, lambda P: flow_part(H, P, 0.0, front=-0.7, down=0.5), lambda P: flow_from(H, P, crown, 0.1), 70, 120)
    b.partline = part_line(H, 0.0, el_min=30, back=-0.03)
    b.tiles = ["messy"] * 16 + ["wavy"] * 8
    gf = b.guard_face(0.004)

    def length(a, e, p):
        a = abs(D_(a)); e = D_(e)
        if a < 50:
            return 0.12
        if a > 120:
            return 0.17 if e < 25 else 0.11
        return 0.12 if e < 25 else 0.09
    b.nap = False
    b.tiles = ["messy"] * 12 + ["sheetwave"] * 4 + ["wavy"] * 8
    b.sheets(lambda a: 0.12 + 0.05 * ss(90, 150, a), part_x=0.0, wave=(0.008, 0.06), grav=0.5, hug=0.75, rise=0.012, guard=gf,
             layers=((0.004, (12, 15)), (0.009, (12, 15))), segs=18, flick=0.012, az_min=48)
    b.locks_(300, lambda az, el, P: el > R_(-40), length, segs=20, lift=0.3, stiff=1.0, grav=0.42, off=(0.004, 0.016), hug=0.55,
             rise=0.02, width=(0.015, 0.005), tiles=(0, 15), guard=gf, min_d=0.0072, flick=0.014, wave=(0.007, 0.05), clump_=0.4,
             frizz=0.0007)
    b.locks_(150, lambda az, el, P: el > R_(25), lambda a, e, p: 0.085, segs=14, lift=0.45, stiff=1.1, grav=0.25, off=(0.014, 0.024),
             hug=0.3, rise=0.025, width=(0.014, 0.004), tiles=(0, 15), min_d=0.009, flick=0.012, clump_=0.45, frizz=0.0007, guard=gf)


def k_afro_taper(b):
    H = b.H
    b.nap = False
    b.vol_tex = "coily"
    thick = lambda az, el: 0.004 + 0.032 * ss(R_(8), R_(50), el) * (1 - 0.35 * ss(R_(100), R_(170), np.abs(az)))
    b.vol_thick = thick
    b.fade = fade_fn([(0, -90), (45, -90), (70, -10), (180, -30)], [(0, -80), (45, -80), (70, 6), (180, -10)], base=0.35)
    b.flow = lambda P: flow_down(H, P)
    b.tiles = ["coily"] * 16 + ["coily"] * 8
    off = lambda a, e, p: (float(thick(np.array(a), np.array(e))) * 0.75, float(thick(np.array(a), np.array(e))) * 1.0 + 0.002)
    b.locks_(620, lambda az, el, P: el > R_(4), lambda a, e, p: 0.022, segs=10, lift=0.85, stiff=1.0, grav=0.02, off=off, hug=0.0,
             width=(0.012, 0.007), curl=(0.0028, 0.0085), ringlet_w=0.8, tiles=(0, 15), min_d=0.0055, frizz=0.0008, ramp=(0.0, 0.2))
    b.locks_(220, lambda az, el, P: el <= R_(8), lambda a, e, p: 0.012, segs=6, lift=0.6, stiff=1.0, grav=0.05, off=(0.002, 0.004),
             width=(0.008, 0.005), curl=(0.0018, 0.006), ringlet_w=0.8, tiles=(16, 23), min_d=0.006, ramp=(0.0, 0.2))


def k_textured_crow(b):
    """Textured crown: messy pushed-up top with volume at the crown, short tapered sides."""
    H = b.H
    b.vol_thick = lambda az, el: 0.003 + 0.009 * ss(R_(12), R_(45), el)
    b.fade = fade_fn([(0, -90), (45, -90), (70, -2), (180, -18)], [(0, -80), (45, -80), (70, 14), (180, 0)], base=0.55)
    up = np.array((0, 0.2, 1.0))
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_back(H, P, -0.3)), (0.5, flow_forward(H, P, 0.0)))
    b.tiles = ["messy"] * 8 + ["spiky"] * 8 + ["straight"] * 8
    top = lambda az, el, P: (el > R_(20)) | ((np.abs(az) < R_(45)) & (el > R_(10)))
    b.locks_(400, top, lambda a, e, p: 0.068 if abs(D_(a)) < 120 else 0.05, segs=12, lift=0.5, stiff=1.25, grav=0.08, off=(0.003, 0.014),
             hug=0.2, rise=0.02, width=(0.012, 0.0035), tiles=(0, 15), clump_=0.6, min_d=0.0058, dir_jitter=0.4, frizz=0.0008,
             curve=None)
    b.locks_(150, lambda az, el, P: (el > R_(4)) & (el <= R_(22)) & (np.abs(az) > R_(45)), 0.022, segs=8, lift=0.15, stiff=1.0, grav=0.2,
             off=(0.002, 0.004), hug=0.8, width=(0.01, 0.005), tiles=(16, 23), min_d=0.007)


def k_side_part_volume(b):
    H = b.H
    px = 0.032
    b.vol_thick = lambda az, el: 0.003 + 0.009 * ss(R_(12), R_(40), el)
    b.fade = fade_fn([(0, -90), (45, -90), (70, -4), (180, -20)], [(0, -80), (45, -80), (70, 12), (180, -2)], base=0.55)
    b.partline = part_line(H, px, width=0.0014, el_min=28, back=0.0)
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_back(H, P, 0.1)), (0.8, flow_part(H, P, px, front=0.0, down=0.2)))
    b.tiles = ["sleek"] * 16 + ["sleek"] * 8
    b.vol_tex = "straight"
    big = lambda az, el, P: (P[:, 0] < px) & ((el > R_(14)) | (np.abs(az) < R_(45)))
    small = lambda az, el, P: (P[:, 0] >= px) & (el > R_(10))

    def lift_fn(a, e, p):
        return 0.55 if (abs(D_(a)) < 35 and p[0] < px) else 0.12
    back = np.array((0.0, 1.0, 0.0))
    b.locks_(340, big, lambda a, e, p: 0.13 if abs(D_(a)) < 60 else 0.1, segs=20, lift=0.12, stiff=1.0, grav=0.12, off=(0.003, 0.015),
             hug=0.65, rise=0.014, width=(0.016, 0.008), tiles=(0, 15), min_d=0.0068, clump_=0.25, lift_fn=lift_fn,
             curve=lambda s, p, d: back * 0.22 * s)
    b.locks_(120, small, 0.08, segs=14, lift=0.08, stiff=1.0, grav=0.2, off=(0.003, 0.01), hug=0.8, rise=0.006, width=(0.014, 0.007),
             tiles=(0, 15), min_d=0.0068)
    b.locks_(160, lambda az, el, P: (el <= R_(16)) & (el > R_(0)) & (np.abs(az) > R_(45)), 0.03, flow=lambda P: flow_back(H, P, 0.3),
             segs=8, lift=0.05, stiff=1.0, grav=0.1, off=(0.002, 0.004), hug=0.9, width=(0.012, 0.006), tiles=(16, 23), min_d=0.007)


def k_mohawk_fade(b):
    H = b.H
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.0016)
    strip = lambda P: 1 - ss(0.026, 0.04, np.abs(P[:, 0]))
    b.fade = lambda az, el, P: np.maximum(strip(P), 0.5 * ss(R_(0), R_(40), el))
    b.tiles = ["spiky"] * 8 + ["messy"] * 8 + ["straight"] * 8
    b.flow = lambda P: flow_back(H, P, 0.0)
    w = lambda az, el, P: np.abs(P[:, 0]) < 0.024
    back = np.array((0.0, 1.0, 0.25))
    b.locks_(240, w, lambda a, e, p: 0.085 if D_(e) > 20 else 0.06, segs=14, lift=0.55, stiff=1.3, grav=0.05, off=(0.003, 0.012),
             hug=0.0, width=(0.013, 0.004), tiles=(0, 15), clump_=0.45, min_d=0.005, curve=lambda s_, p, d: back * 0.12 * s_)
    b.locks_(120, lambda az, el, P: np.abs(P[:, 0]) < 0.034, 0.03, segs=8, lift=0.3, stiff=1.0, grav=0.05, off=(0.002, 0.005),
             hug=0.5, width=(0.01, 0.004), tiles=(16, 23), min_d=0.006)


def k_burst_fade_mohawk(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.002 + 0.006 * ss(R_(30), R_(60), el)
    ear = [np.array((s * (H.half_w + 0.005), H.hc[1] + 0.005, H.hc[2] - 0.02)) for s in (1, -1)]

    def fade(az, el, P):
        d = np.minimum(np.linalg.norm(P - ear[0], axis=1), np.linalg.norm(P - ear[1], axis=1))
        strip = 1 - ss(0.04, 0.055, np.abs(P[:, 0]))
        burst = ss(0.035, 0.07, d)
        return np.maximum(strip, burst * 0.85)
    b.fade = fade
    b.vol_tex = "curly"
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_forward(H, P, 0.0)), (0.6, flow_back(H, P, -0.5)))
    b.tiles = ["curly"] * 16 + ["coily"] * 8
    w = lambda az, el, P: (np.abs(P[:, 0]) < 0.042) & (el > R_(-10))
    b.locks_(330, w, lambda a, e, p: 0.06 if D_(e) > 15 else 0.035, segs=18, lift=0.6, stiff=1.1, grav=0.05, off=(0.003, 0.014),
             hug=0.1, rise=0.02, curl=(0.0042, 0.015), ringlet_w=0.7, tiles=(0, 15), min_d=0.0058, frizz=0.0005)
    b.locks_(160, lambda az, el, P: (np.abs(P[:, 0]) >= 0.036) & (el > R_(-30)), 0.012, segs=6, lift=0.4, stiff=1.0, grav=0.05,
             off=(0.002, 0.003), width=(0.008, 0.005), curl=(0.0016, 0.006), ringlet_w=0.8, tiles=(16, 23), min_d=0.0065,
             weight=lambda c: fade(None, None, c))


def k_edgy_caesar(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.002 + 0.004 * ss(R_(24), R_(44), el)
    b.fade = fade_fn([(0, -90), (40, -90), (60, 2), (180, -12)], [(0, -80), (40, -80), (60, 22), (180, 8)])
    b.flow = lambda P: flow_forward(H, P, 0.25, spread=0.3)
    b.tiles = ["messy"] * 8 + ["straight"] * 8 + ["straight"] * 8
    gb = b.guard_brow(0.046, 0.0015)
    top = lambda az, el, P: (el > R_(30)) | ((np.abs(az) < R_(40)) & (el > R_(12)))
    b.locks_(480, top, lambda a, e, p: 0.032, segs=8, lift=0.12, stiff=1.1, grav=0.08, off=(0.002, 0.008), hug=0.85, rise=0.004,
             width=(0.01, 0.005), tiles=(0, 15), guard=gb, min_d=0.005, clump_=0.35)


def k_ivy_league(b):
    H = b.H
    px = 0.036
    b.vol_thick = lambda az, el: 0.003 + 0.006 * ss(R_(15), R_(40), el)
    b.fade = fade_fn([(0, -90), (45, -90), (70, -4), (180, -20)], [(0, -80), (45, -80), (70, 14), (180, 0)], base=0.5)
    b.partline = part_line(H, px, width=0.0009, el_min=30, back=-0.01)
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_part(H, P, px, front=0.0, down=0.25)), (0.5, flow_back(H, P, 0.0)))
    b.tiles = ["straight"] * 16 + ["straight"] * 8

    def lift_fn(a, e, p):
        return 0.35 if (abs(D_(a)) < 35 and p[0] < px) else 0.1
    top = lambda az, el, P: (el > R_(20)) | ((np.abs(az) < R_(45)) & (el > R_(10)))
    b.locks_(400, top, lambda a, e, p: 0.07 if abs(D_(a)) < 70 else 0.055, segs=14, lift=0.12, stiff=1.1, grav=0.12, off=(0.003, 0.012),
             hug=0.7, rise=0.008, width=(0.013, 0.006), tiles=(0, 15), min_d=0.006, clump_=0.25, lift_fn=lift_fn)
    b.locks_(150, lambda az, el, P: (el <= R_(22)) & (el > R_(0)) & (np.abs(az) > R_(45)), 0.025, segs=8, lift=0.05, stiff=1.0, grav=0.2,
             off=(0.002, 0.004), hug=0.9, width=(0.011, 0.005), tiles=(16, 23), min_d=0.007)


def k_french_crop_design(b):
    H = b.H
    b.vol_thick = lambda az, el: 0.002 + 0.006 * ss(R_(22), R_(42), el)
    b.fade = fade_fn([(0, -90), (40, -90), (60, -4), (180, -20)], [(0, -80), (40, -80), (60, 12), (180, 0)])
    zig = [(-0.05, 0.022), (-0.035, 0.03), (-0.02, 0.018), (-0.005, 0.03), (0.01, 0.018), (0.025, 0.03), (0.04, 0.016), (0.06, 0.012)]
    b.design = side_design(H, [zig, [(-0.045, 0.012), (0.0, 0.006), (0.05, 0.0)]], width=0.0015)
    b.flow = lambda P: flow_forward(H, P, 0.4, spread=0.4)
    b.tiles = ["straight"] * 8 + ["messy"] * 8 + ["straight"] * 8
    gb = b.guard_brow(0.022, 0.002)
    top = lambda az, el, P: (el > R_(30)) | ((np.abs(az) < R_(45)) & (el > R_(10)))
    b.locks_(440, top, lambda a, e, p: 0.06 if abs(D_(a)) < 40 else 0.045, segs=12, lift=0.18, stiff=1.1, grav=0.15, off=(0.003, 0.011),
             hug=0.75, rise=0.006, width=(0.012, 0.005), tiles=(0, 15), guard=gb, min_d=0.0055, clump_=0.3, frizz=0.0003)


def k_emo_fringe(b):
    H = b.H
    b.face_clip = False
    b.kind = "skinned"
    b.vol_thick = lambda az, el: 0.005 + 0.008 * ss(R_(5), R_(40), el)
    sweep = lambda P: H.tangent(P, np.stack([np.full(len(P), -1.0), np.full(len(P), -0.45), np.full(len(P), -0.55)], 1))
    crown = crown_pt(H, 175, 58)
    b.flow = front_back_flow(H, sweep, lambda P: flow_from(H, P, crown, 0.2), 70, 115)
    b.tiles = ["sleek"] * 8 + ["straight"] * 8 + ["wisp"] * 8
    gf = b.guard_face(0.006, cover=(-1, H.eye[2] - 0.035))
    b.locks_(200, lambda az, el, P: (np.abs(az) < R_(75)) & (el > R_(10)), lambda a, e, p: 0.17 if p[0] > -0.02 else 0.12, segs=22,
             lift=0.12, stiff=1.0, grav=0.45, off=(0.004, 0.016), hug=0.75, rise=0.008, width=(0.013, 0.0045), tiles=(0, 15),
             guard=gf, min_d=0.0068, clump_=0.35)
    b.nap = False
    b.sheets(lambda a: 0.1 + 0.035 * ss(90, 150, a), part_x=None, grav=0.6, hug=0.85, rise=0.006, layers=((0.004, (0, 7)), (0.009, (8, 15))),
             segs=16, az_min=70, crown_el=50, guard=gf)
    b.locks_(300, lambda az, el, P: np.abs(az) >= R_(60), lambda a, e, p: 0.13 if abs(D_(a)) > 120 else 0.1, segs=18, lift=0.1, stiff=1.0,
             grav=0.5, off=(0.004, 0.016), hug=0.75, rise=0.008, width=(0.014, 0.004), tiles=(0, 15), guard=gf, min_d=0.007, clump_=0.4,
             flick=0.004)


# ============================================================================= GIVA (lyra)


def l_long_curls(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.38
    b.vol_tex = "curly"
    b.vol_thick = lambda az, el: 0.006 + 0.01 * ss(R_(0), R_(40), el)
    b.vol_lum = 0.55
    b.flow = lambda P: flow_part(H, P, 0.028, front=0.1, down=0.75)
    b.partline = part_line(H, 0.028, el_min=36, back=-0.02)
    b.tiles = ["curly"] * 16 + ["wavy"] * 8
    gf = b.guard_face(0.016)
    b.nap = False
    b.tiles = ["sheetcurl"] * 8 + ["curly"] * 8 + ["wavy"] * 8
    b.sheets(lambda a: 0.36 if a < 70 else 0.42, part_x=0.028, wave=(0.012, 0.06), curl_amp=0.006, guard=gf, rise=0.01,
             layers=((0.004, (0, 3)), (0.009, (4, 7)), (0.014, (2, 7))))
    long_layers(b, 0.42, None, tiles=(8, 15), wave=(0.012, 0.045), guard=gf, rise=0.014, ramp=(0.12, 0.4),
                width=(0.022, 0.011), n_scale=0.8)


def l_long_waves(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.35
    b.vol_thick = lambda az, el: 0.006 + 0.008 * ss(R_(0), R_(40), el)
    b.vol_lum = 0.55
    b.flow = lambda P: flow_part(H, P, 0.028, front=0.1, down=0.75)
    b.tiles = ["wavy"] * 16 + ["wisp"] * 8
    b.partline = part_line(H, 0.028, el_min=36, back=-0.02)
    gf = b.guard_face(0.014)
    b.nap = False
    b.tiles = ["sheetwave"] * 10 + ["wavy"] * 6 + ["wisp"] * 8
    b.sheets(lambda a: 0.36 if a < 70 else 0.43, part_x=0.028, wave=(0.013, 0.085), guard=gf, rise=0.01,
             layers=((0.004, (0, 4)), (0.009, (5, 9)), (0.014, (2, 9))))
    long_layers(b, 0.42, None, tiles=(10, 15), wave=(0.014, 0.085), guard=gf, rise=0.014, lift=0.12, n_scale=0.45)


def l_sleek_long(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.35
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.004)
    b.vol_lum = 0.6
    b.flow = lambda P: flow_part(H, P, 0.0, front=0.15, down=0.85)
    b.partline = part_line(H, 0.0, el_min=34, back=-0.03)
    b.tiles = ["sleek"] * 16 + ["sleek"] * 8
    gf = b.guard_face(0.012)
    zc = H.shoulder_z - 0.2
    cutf = lambda P: P[:, 2] < zc + 0.03 * np.abs(P[:, 0]) / 0.1 - 0.02 * (P[:, 1] > H.hc[1] + 0.05)
    b.nap = False
    b.tiles = ["sheet"] * 10 + ["sleek"] * 6 + ["sleek"] * 8
    b.sheets(0.5, part_x=0.0, guard=gf, rise=0.003, hug=1.1, grav=0.95, cutf=cutf, layers=((0.004, (0, 4)), (0.008, (5, 9)), (0.012, (0, 9))))
    long_layers(b, 0.5, None, tiles=(10, 15), guard=gf, rise=0.004, lift=0.04, grav=0.9, hug=1.1, width=(0.026, 0.016), cutf=cutf,
                frame_short=0.85, n_scale=0.4)


def l_high_ponytail(b):
    H = b.H
    b.nap = False
    b.kind = "skinned"
    b.cutoff = 0.38
    A = b.anchor(180, 42, 0.004)
    b.flow = lambda P: flow_to(H, P, A)
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.0025)
    b.vol_lum = 0.6
    b.tiles = ["sleek"] * 16 + ["wavy"] * 8
    b.gather(330, lambda az, el, P: np.ones(len(az), bool), A, off=(0.0025, 0.007), width=(0.018, 0.014), min_d=0.0075)
    nA = H.radial(A[None])[0]
    b.tail(A + nA * 0.008, nA * 0.45 + np.array((0, 0.6, 0.05)), 0.4, n=110, r0=0.011, r1=0.03, grav=2.4, wave=(0.008, 0.11),
           tiles=(16, 23), width=(0.022, 0.012), clear=0.022)
    b.wrap(A + nA * 0.006, nA, radius=0.0135, tile=4)


def l_braided_crown(b):
    H = b.H
    b.nap = False
    b.cutoff = 0.38
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.003)
    b.vol_lum = 0.62
    ring_el = lambda a: np.interp(np.abs(np.degrees(a)), [0, 60, 100, 140, 180], [40, 28, 14, 4, 0])

    def ring_pts(P):
        a, e, r = H.angles(P)
        return H.surf(a, R_(ring_el(a)), 0.008)

    def ring_pt(p):
        return ring_pts(p[None])[0]
    b.flow = lambda P: flow_to(H, P, ring_pts(P))
    b.tiles = ["sleek"] * 12 + ["braid"] * 4 + ["wisp"] * 8
    b.locks_(360, lambda az, el, P: np.ones(len(az), bool), 0.25, flow=None, segs=18, lift=0.02, stiff=0.55, grav=0.0, off=(0.0025, 0.007),
             hug=1.2, width=(0.017, 0.013), tiles=(0, 11), attract=ring_pt, att_k=0.45, stop_r=0.012, min_d=0.0075, jitter=0.0,
             dir_jitter=0.03)
    az = np.radians(np.linspace(-178, 178, 90))
    path = H.surf(az, R_(ring_el(az)), 0.011)
    braid3(H, b.part, path, 0.03, 12, 1.0, b.rng, flat=0.55, taper=0.05, period=0.055)
    gf = b.guard_face(0.01)
    b.locks_(14, lambda az, el, P: (np.abs(az) > R_(55)) & (np.abs(az) < R_(80)) & (el < R_(20)), 0.15, flow=lambda P: flow_down(H, P),
             segs=18, lift=0.1, stiff=1.0, grav=0.7, off=(0.006, 0.01), hug=0.6, width=(0.01, 0.004), tiles=(16, 23),
             wave=(0.012, 0.06), guard=gf, min_d=0.006)


def l_fishtail_braid(b):
    H = b.H
    b.nap = False
    b.kind = "skinned"
    b.cutoff = 0.38
    A = b.anchor(180, -20, 0.01)
    b.vol_thick = lambda az, el: 0.004 + 0.005 * ss(R_(10), R_(40), el)
    b.vol_lum = 0.6
    b.flow = lambda P: blend_flows(H, P, (1.0, flow_to(H, P, A)), (0.3, flow_part(H, P, -0.03, 0.0, 0.0)))
    b.partline = part_line(H, -0.03, el_min=38, back=-0.03)
    b.tiles = ["sleek"] * 12 + ["braid"] * 4 + ["wavy"] * 8
    b.gather(360, lambda az, el, P: np.ones(len(az), bool), A, off=(0.003, 0.012), width=(0.018, 0.013), min_d=0.0072, hug=0.9,
             loose=0.2, tiles=(0, 11))
    nA = H.radial(A[None])[0]
    axis = back_path(H, A + nA * 0.008, 0.34, x=0.004, clear=0.024)
    fishtail(H, b.part, axis, 0.046, 12, 1.0, b.rng, taper=0.45)
    end = axis[-1]
    T = nrm(axis[-1] - axis[-3])
    b.tail(end - T * 0.01, T, 0.07, n=40, r0=0.008, r1=0.014, grav=1.5, tiles=(16, 23), width=(0.014, 0.006), clear=0.02, end_taper=0.8)
    gf = b.guard_face(0.01)
    b.locks_(16, lambda az, el, P: (np.abs(az) > R_(50)) & (np.abs(az) < R_(80)) & (el < R_(22)), 0.17, flow=lambda P: flow_down(H, P),
             segs=18, lift=0.1, stiff=1.0, grav=0.7, off=(0.006, 0.012), hug=0.6, width=(0.011, 0.004), tiles=(16, 23),
             wave=(0.012, 0.06), guard=gf, min_d=0.006)


def l_space_buns(b):
    H = b.H
    b.nap = False
    b.cutoff = 0.38
    AL = b.anchor(58, 50, 0.005)
    AR = b.anchor(-58, 50, 0.005)
    b.partline = part_line(H, 0.0, el_min=20, back=0.2)
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.003)
    b.vol_lum = 0.62
    b.flow = lambda P: np.where((P[:, 0] >= 0)[:, None], flow_to(H, P, AL), flow_to(H, P, AR))
    b.tiles = ["sleek"] * 12 + ["wavy"] * 4 + ["wisp"] * 8
    for A, sg in ((AL, 1), (AR, -1)):
        b.gather(200, lambda az, el, P, sg=sg: (P[:, 0] * sg) > 0.0005, A, off=(0.0025, 0.007), width=(0.017, 0.013), tiles=(0, 11),
                 min_d=0.0072)
        nA = H.radial(A[None])[0]
        bun_geo(H, b.part, A + nA * 0.026, nA, 0.03, (12, 15), 1.0, b.rng, cards=90, messy=0.1)
    gf = b.guard_face(0.01)
    b.locks_(18, lambda az, el, P: (np.abs(az) > R_(45)) & (np.abs(az) < R_(80)) & (el < R_(24)), 0.14, flow=lambda P: flow_down(H, P),
             segs=18, lift=0.1, stiff=1.0, grav=0.7, off=(0.006, 0.012), hug=0.6, width=(0.011, 0.004), tiles=(16, 23),
             wave=(0.012, 0.055), guard=gf, min_d=0.006)


def l_bob_wavy(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.36
    b.vol_thick = lambda az, el: 0.006 + 0.01 * ss(R_(0), R_(40), el)
    b.vol_lum = 0.58
    b.flow = lambda P: flow_part(H, P, 0.03, front=0.05, down=0.75)
    b.partline = part_line(H, 0.03, el_min=36, back=-0.02)
    b.tiles = ["wavy"] * 16 + ["wisp"] * 8
    gf = b.guard_face(0.014)
    zc = H.jaw_z - 0.005
    ph = b.rng.uniform(0, 6.28)
    cutf = lambda P: P[:, 2] < zc - 0.025 * ss(H.hc[1], H.hc[1] - 0.08, P[:, 1]) + 0.004 * np.sin(P[:, 0] * 700 + ph)
    b.nap = False
    b.tiles = ["sheetwave"] * 10 + ["wavy"] * 6 + ["wisp"] * 8
    b.sheets(0.27, part_x=0.03, wave=(0.012, 0.06), guard=gf, rise=0.014, grav=0.6, hug=0.8, cutf=cutf, flick=0.008, segs=20,
             layers=((0.004, (0, 4)), (0.009, (5, 9)), (0.014, (2, 9))), az_min=36)
    long_layers(b, 0.26, None, tiles=(10, 15), wave=(0.013, 0.06), guard=gf, rise=0.016, lift=0.18, grav=0.55, hug=0.75, cutf=cutf,
                frame_short=1.0, flick=0.006, width=(0.022, 0.012), n_scale=0.5)


def l_pixie(b):
    H = b.H
    b.face_clip = False
    b.vol_thick = lambda az, el: 0.003 + 0.008 * ss(R_(10), R_(40), el)
    b.fade = fade_fn([(0, -90), (60, -90), (80, -10), (180, -36)], [(0, -80), (60, -80), (80, 4), (180, -20)], base=0.6)
    side = lambda P: H.tangent(P, np.stack([np.full(len(P), -1.0), np.full(len(P), -0.5), np.full(len(P), -0.35)], 1))
    crown = crown_pt(H, 178, 55)
    b.flow = front_back_flow(H, side, lambda P: flow_from(H, P, crown, 0.15), 70, 120)
    b.tiles = ["straight"] * 8 + ["messy"] * 8 + ["wisp"] * 8
    gf = b.guard_face(0.004, cover=(-1, H.eye[2] + 0.004))
    b.locks_(230, lambda az, el, P: (np.abs(az) < R_(70)) & (el > R_(10)), lambda a, e, p: 0.1 if p[0] > -0.03 else 0.07, segs=16,
             lift=0.2, stiff=1.0, grav=0.3, off=(0.004, 0.015), hug=0.7, rise=0.012, width=(0.013, 0.004), tiles=(0, 15), guard=gf,
             min_d=0.0065, clump_=0.4, flick=0.003)
    b.locks_(300, lambda az, el, P: np.abs(az) >= R_(60), lambda a, e, p: 0.06 if D_(e) > 15 else 0.035, segs=12, lift=0.15, stiff=1.0,
             grav=0.25, off=(0.003, 0.012), hug=0.75, rise=0.008, width=(0.012, 0.004), tiles=(0, 15), min_d=0.0065, clump_=0.4,
             guard=gf)


def l_side_shave_long(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.36
    shaved = lambda az, el, P: (P[:, 0] < -0.03) & (np.degrees(np.abs(az)) > 35) & (np.degrees(np.abs(az)) < 160) & (el < R_(36))
    b.fade = lambda az, el, P: np.where(shaved(az, el, P), 0.3 + 0.35 * ss(R_(25), R_(36), el), 1.0)
    b.design = side_design(H, [[(-0.04, 0.03), (0.0, 0.034), (0.05, 0.02)], [(-0.03, 0.018), (0.01, 0.022), (0.055, 0.008)],
                               [(-0.02, 0.006), (0.02, 0.01), (0.06, -0.004)]], width=0.0013, sides=(-1,), xmin=0.04)
    b.vol_thick = lambda az, el: 0.005 + 0.007 * ss(R_(0), R_(40), el)
    b.vol_lum = 0.58
    sweep = lambda P: H.tangent(P, np.stack([np.full(len(P), 1.0), np.full(len(P), 0.25), np.full(len(P), -0.5)], 1))
    b.flow = sweep
    b.partline = part_line(H, -0.03, el_min=36, back=-0.02)
    b.tiles = ["wavy"] * 16 + ["wisp"] * 8
    gf = b.guard_face(0.016)
    keep = lambda az, el, P: ~shaved(az, el, P) & ~((P[:, 0] < -0.025) & (el < R_(40)) & (np.abs(az) > R_(30)))
    b.nap = False
    b.tiles = ["sheetwave"] * 10 + ["wavy"] * 6 + ["wisp"] * 8
    b.sheets(lambda a: 0.42, part_x=-0.03, wave=(0.012, 0.09), guard=gf, rise=0.012, sides=(1,), az_min=30,
             layers=((0.004, (0, 4)), (0.009, (5, 9)), (0.014, (2, 9))))
    long_layers(b, 0.42, sweep, tiles=(10, 15), wave=(0.012, 0.09), guard=gf, rise=0.016, lift=0.2, where=keep, n_scale=0.7)


def l_wolf_cut_long(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.36
    b.vol_thick = lambda az, el: 0.007 + 0.012 * ss(R_(10), R_(45), el)
    b.vol_lum = 0.58
    crown = crown_pt(H, 180, 60)
    b.flow = front_back_flow(H, lambda P: flow_part(H, P, 0.0, front=-0.6, down=0.6), lambda P: flow_from(H, P, crown, 0.2), 70, 120)
    b.partline = part_line(H, 0.0, el_min=32, back=-0.03)
    b.tiles = ["messy"] * 16 + ["wavy"] * 8
    gf = b.guard_face(0.008)

    def length(a, e, p):
        a = abs(D_(a)); e = D_(e)
        if a < 50:
            return 0.14
        if e > 30:
            return 0.12
        return 0.3 if a > 110 else 0.22
    b.nap = False
    b.tiles = ["messy"] * 10 + ["sheetwave"] * 6 + ["wavy"] * 8
    b.sheets(lambda a: 0.16 if a < 60 else (0.22 if a < 110 else 0.29), part_x=0.0, wave=(0.009, 0.06), guard=gf, rise=0.016, flick=0.016,
             layers=((0.004, (10, 15)), (0.009, (10, 15)), (0.014, (10, 15))), az_min=40)
    b.locks_(380, lambda az, el, P: el > R_(-40), length, segs=24, lift=0.25, stiff=1.0, grav=0.5, off=(0.004, 0.018), hug=0.6,
             rise=0.02, width=(0.017, 0.005), tiles=(0, 15), guard=gf, min_d=0.0072, flick=0.016, wave=(0.009, 0.06), clump_=0.4,
             frizz=0.0008)
    b.locks_(170, lambda az, el, P: el > R_(25), lambda a, e, p: 0.1, segs=14, lift=0.45, stiff=1.1, grav=0.3, off=(0.016, 0.026),
             hug=0.3, rise=0.025, width=(0.015, 0.004), tiles=(0, 15), min_d=0.009, flick=0.014, clump_=0.45, frizz=0.0008, guard=gf)


def l_curtain_bangs_long(b):
    H = b.H
    b.kind = "skinned"
    b.cutoff = 0.36
    b.vol_thick = lambda az, el: 0.006 + 0.008 * ss(R_(0), R_(40), el)
    b.vol_lum = 0.58
    b.flow = lambda P: flow_part(H, P, 0.0, front=0.1, down=0.8)
    b.partline = part_line(H, 0.0, el_min=30, back=-0.02)
    b.tiles = ["straight"] * 8 + ["wavy"] * 8 + ["wisp"] * 8
    gf = b.guard_face(0.008)
    bang = lambda az, el, P: (np.abs(az) < R_(45)) & (el > R_(20))
    for n, off in ((70, (0.004, 0.01)), (60, (0.01, 0.017))):
        side_k = lambda s_, p, d: np.array((math.copysign(0.9, p[0] if abs(p[0]) > 1e-4 else 1.0) * ss(0.15, 0.7, s_), 0.0, 0.0))
        b.locks_(n, bang, 0.15, flow=lambda P: flow_down(H, P), segs=22, lift=0.0, stiff=0.8, grav=0.6, off=off,
                 hug=1.6, rise=0.002, width=(0.016, 0.006), tiles=(0, 15), guard=gf, min_d=0.007, wave=(0.004, 0.07), curve=side_k)
    b.nap = False
    b.tiles = ["straight"] * 8 + ["sheetwave"] * 8 + ["wisp"] * 8
    b.sheets(0.44, part_x=0.0, wave=(0.006, 0.12), guard=gf, rise=0.01, layers=((0.004, (8, 11)), (0.009, (12, 15)), (0.014, (8, 15))), az_min=45)
    long_layers(b, 0.44, None, tiles=(0, 15), wave=(0.006, 0.12), guard=gf, rise=0.01, lift=0.1, n_scale=0.4,
                where=lambda az, el, P: ~((np.abs(az) < R_(40)) & (el > R_(20))))


def l_twin_tails(b):
    H = b.H
    b.nap = False
    b.kind = "skinned"
    b.cutoff = 0.38
    AL = b.anchor(118, 8, 0.006)
    AR = b.anchor(-118, 8, 0.006)
    b.partline = part_line(H, 0.0, el_min=10, back=0.2)
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.003)
    b.vol_lum = 0.62
    b.flow = lambda P: np.where((P[:, 0] >= 0)[:, None], flow_to(H, P, AL), flow_to(H, P, AR))
    b.tiles = ["sleek"] * 12 + ["wavy"] * 4 + ["wavy"] * 8
    for A, sg in ((AL, 1), (AR, -1)):
        b.gather(200, lambda az, el, P, sg=sg: (P[:, 0] * sg) > 0.0005, A, off=(0.0025, 0.008), width=(0.017, 0.013), tiles=(0, 11),
                 min_d=0.0072)
        nA = H.radial(A[None])[0]
        b.tail(A + nA * 0.008, nA * 0.7 + np.array((0, 0.3, -0.3)), 0.34, n=85, r0=0.01, r1=0.028, grav=2.2, wave=(0.01, 0.09),
               tiles=(16, 23), width=(0.02, 0.011), clear=0.024)
        b.wrap(A + nA * 0.006, nA, radius=0.012, tile=13)
    gf = b.guard_face(0.012)
    b.locks_(60, lambda az, el, P: (np.abs(az) < R_(40)) & (el > R_(20)), 0.11, flow=lambda P: flow_forward(H, P, 0.4, spread=1.4), segs=18,
             lift=0.2, stiff=1.0, grav=0.4, off=(0.006, 0.013), hug=0.6, rise=0.01, width=(0.013, 0.005), tiles=(0, 11),
             guard=b.guard_brow(0.006, 0.006), min_d=0.0068)


def l_messy_bun(b):
    H = b.H
    b.nap = False
    b.cutoff = 0.38
    A = b.anchor(180, 56, 0.006)
    b.vol_thick = lambda az, el: np.full(np.shape(az), 0.004)
    b.vol_lum = 0.6
    b.flow = lambda P: flow_to(H, P, A)
    b.tiles = ["messy"] * 12 + ["wavy"] * 4 + ["wisp"] * 8
    b.gather(380, lambda az, el, P: np.ones(len(az), bool), A, off=(0.003, 0.012), width=(0.017, 0.012), tiles=(0, 11), min_d=0.0068,
             hug=0.7, loose=1.0)
    nA = H.radial(A[None])[0]
    bun_geo(H, b.part, A + nA * 0.03, nA * 0.8 + np.array((0, 0.25, 0.2)), 0.036, (12, 15), 1.0, b.rng, cards=120, messy=1.0, wraps=3.5)
    gf = b.guard_face(0.008)
    b.locks_(26, lambda az, el, P: (np.abs(az) > R_(40)) & (np.abs(az) < R_(85)) & (el < R_(28)), 0.15, flow=lambda P: flow_down(H, P),
             segs=18, lift=0.12, stiff=1.0, grav=0.7, off=(0.006, 0.012), hug=0.6, width=(0.011, 0.004), tiles=(16, 23),
             wave=(0.013, 0.055), guard=gf, min_d=0.006)
    b.locks_(16, lambda az, el, P: (np.abs(az) > R_(150)) & (el < R_(-20)), 0.07, flow=lambda P: flow_down(H, P), segs=10, lift=0.1,
             stiff=1.0, grav=0.6, off=(0.004, 0.008), hug=0.6, width=(0.009, 0.004), tiles=(16, 23), wave=(0.008, 0.04), min_d=0.008)


KAEL = {
    "textured_fringe": ("Textured Fringe", k_textured_fringe),
    "korean_perm": ("Korean Perm", k_korean_perm),
    "mullet_fade": ("Mullet Fade", k_mullet_fade),
    "curtain_bangs": ("Curtain Bangs", k_curtain_bangs),
    "two_block": ("Two Block", k_two_block),
    "textured_crop_design": ("Textured Crop + Design", k_textured_crop_design),
    "flowing_waves": ("Flowing Waves", k_flowing_waves),
    "modern_bowl": ("Modern Bowl", k_modern_bowl),
    "man_bun_fade": ("Braided Man Bun Fade", k_man_bun_fade),
    "wolf_cut": ("Wolf Cut", k_wolf_cut),
    "afro_taper": ("Soft Afro Taper", k_afro_taper),
    "textured_crow": ("Textured Crown", k_textured_crow),
    "side_part_volume": ("Slicked Side Part", k_side_part_volume),
    "mohawk_fade": ("Mohawk Fade", k_mohawk_fade),
    "burst_fade_mohawk": ("Burst Fade Mohawk", k_burst_fade_mohawk),
    "edgy_caesar": ("Edgy Caesar", k_edgy_caesar),
    "ivy_league": ("Ivy League", k_ivy_league),
    "french_crop_design": ("French Crop + Design", k_french_crop_design),
    "emo_fringe": ("Emo Fringe", k_emo_fringe),
    "curly_medium": ("Defined Medium Curls", k_curly_medium),
}
LYRA = {
    "long_curls": ("Long Curls", l_long_curls),
    "long_waves": ("Long Waves", l_long_waves),
    "sleek_long": ("Sleek Long", l_sleek_long),
    "high_ponytail": ("High Ponytail", l_high_ponytail),
    "braided_crown": ("Braided Crown", l_braided_crown),
    "fishtail_braid": ("Fishtail Braid", l_fishtail_braid),
    "space_buns": ("Space Buns", l_space_buns),
    "bob_wavy": ("Wavy Bob", l_bob_wavy),
    "pixie": ("Pixie Cut", l_pixie),
    "side_shave_long": ("Side Shave Long", l_side_shave_long),
    "wolf_cut_long": ("Long Wolf Cut", l_wolf_cut_long),
    "curtain_bangs_long": ("Long Curtain Bangs", l_curtain_bangs_long),
    "twin_tails": ("Twin Tails", l_twin_tails),
    "messy_bun": ("Messy Bun", l_messy_bun),
}
DEFAULTS = {"kael": "side_part_volume", "lyra": "long_waves"}
