"""Kael v3 built-in hair 'swept_fade' (concept match): dark-brown top swept back and over to his right with a loose fringe
lock falling towards the right brow; his left side is shaved short (the cap is transparent there; the grey/silver buzz
is painted into the skin texture by skin_k2). Built with the hair v4 card library (blender/custom, read-only use) on
the Kael v3 head, run in its own Blender process (the custom libs share module names with blender/scripts).

  blender -b blends/kael_s6_deform.blend --python scripts/hair_k3.py
Writes blends/hair_k3.blend (object Hair_swept_fade, Head-rigid) and tex/Hair_swept_fade_Color.png (RGBA, grey).
"""
import bpy, os, sys, math, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
KROOT = os.path.abspath(os.path.join(HERE, ".."))
CUSTOM = os.path.abspath(os.path.join(KROOT, "..", "..", "custom"))
sys.path.insert(0, CUSTOM)
sys.path.insert(1, os.path.join(CUSTOM, "lib"))
import numpy as np
from mathutils import Vector
import common as C
import gear
import hair_v4 as HV
import hairlib as HL
from hairlib import Head, grow, volume_shell
from common import ss, nrm

R_ = np.radians
STYLE = "swept_fade"
PART_X = 0.034            # parting on his left (+x); the top sweeps over to his right (-x)


def shaved(P, az_, el_, H):
    """1 on his shaved left side below the parting line, 0 elsewhere (soft edge)."""
    side = ss(PART_X + 0.006, PART_X + 0.022, P[:, 0])
    low = 1 - ss(R_(30), R_(40), el_)
    back = 1 - ss(R_(130), R_(165), np.abs(az_))
    return side * low * back


def build(b):
    H, rng = b.H, b.rng
    b.kind = "rigid"
    b.cutoff = 0.4
    hairline = [30, 28, 24, 13, 5, -8, -24, -31, -34]
    cap_line = [k - 6 for k in hairline]
    mask, az, el = H.scalp(cap_line)

    def big(P):
        return P[:, 0] < PART_X

    def flow(P):
        az_, el_, r_ = H.angles(P)
        side = np.where(big(P), -1.0, 1.0)
        top = ss(R_(18), R_(50), el_)
        back = ss(R_(80), R_(150), np.abs(az_))
        F = np.stack([side * (0.62 + 0.4 * top) * (1 - 0.5 * back), 0.5 + 0.35 * back, -0.25 - 0.8 * (1 - top)], 1)
        return H.tangent(P, F)

    def dens(az_, el_, P):
        a = np.degrees(np.abs(az_))
        lo = np.interp(a, [0, 45, 70, 110, 150, 180], [-40, -40, -6, -8, -22, -26])
        hi = np.interp(a, [0, 45, 70, 110, 150, 180], [-30, -30, 18, 16, 2, -2])
        d = 0.08 + 0.92 * ss(R_(lo), R_(hi), el_)
        return d * (1 - shaved(P, az_, el_, H))

    def brow_guard(q, p):
        # the fringe lock may fall onto the forehead on his right, but never below the brows / over the eyes
        if q[2] < H.brow_z + 0.008 and abs(q[0]) < H.face_hw + 0.01 and q[1] < H.eye[1] + 0.03:
            return None
        if q[0] > -0.01 and q[1] < H.eye[1] + 0.03:
            a_, e_, _ = H.angles(q[None])
            if abs(a_[0]) < R_(72) and e_[0] < H.hairline_el(a_, hairline)[0] + R_(1.0):
                return None
        return q

    vol = volume_shell(H, b.ctx, b.sid + "_cap", mask,
                       lambda a_, e_: 0.0015 + 0.0048 * ss(R_(12), R_(42), e_) * (1 - 0.5 * ss(R_(100), R_(170), np.abs(a_))))
    cm = H.scalp(hairline)[0]
    co = b.ctx.basis
    tiles_top = list(range(0, 12))
    tiles_side = list(range(12, 20))
    wisp = [20, 21]
    fringe_t = [22, 23]
    # ---------------- top: layered swept cards with volume, longer at the front, a falling fringe lock on his right
    for li, (n, off0, off1, lift, Lm) in enumerate([(185, 0.0024, 0.0045, 0.12, 1.08), (140, 0.0052, 0.0078, 0.19, 1.02),
                                                    (95, 0.008, 0.0108, 0.24, 0.95)]):
        zone = cm & ((el > R_(24)) | ((np.abs(az) < R_(55)) & (el > R_(14))))
        roots, rn = H.sample_roots(zone, n, 0.0056, seed=11 + 13 * li)
        F0 = flow(roots)
        for p, nn, f in zip(roots, rn, F0):
            a_, e_, _ = H.angles(p[None]); ad = abs(math.degrees(a_[0])); ed = math.degrees(e_[0])
            if float(shaved(p[None], a_, e_, H)[0]) > 0.5:
                continue
            front = ad < 50
            L = (0.15 if front else 0.1 - 0.03 * ss(90, 160, ad)) * Lm * rng.uniform(0.88, 1.1)
            L *= 1 - 0.45 * ss(45, 100, ad) * (1 - ss(28, 50, ed))      # short at the sides (no curtain over the temple)
            if p[0] >= PART_X:
                L *= 0.72
            lf = lift + (0.32 if front and ed < 42 else 0.06)
            backv = np.array((np.sign(PART_X - p[0]) * 0.45, 1.0, 0.1))
            fall = front and -0.034 < p[0] < 0.0 and 32 < ed < 52 and rng.random() < 0.55
            if fall:
                # fringe lock: rises off the forehead, then curls over and down to the right temple
                curve = (lambda s_, q, d: np.array((-0.55, 0.25, -0.75)) * 0.55 * ss(0.35, 0.95, s_))
                lf = 0.18
                L *= 1.15
            else:
                curve = (lambda s_, q, d, bv=backv: bv * 0.35 * ss(0.05, 0.6, s_)) if front else None
            off = rng.uniform(off0, off1)
            hg = 0.75 + 0.6 * ss(50, 90, ad)
            Pp = grow(H, p, nrm(nn * 0.4 + H.radial(p[None])[0] * 0.6), L, f + rng.normal(0, 0.03, 3), 8, lf, 1.25, 0.08, off, hg,
                      0.005, None, 0.0, 0.0, clear=off * 0.75, guard=brow_guard, body_clear=0.006, curve=curve)
            if len(Pp) < 4:
                continue
            Pp = np.array([Pp[0]] + [H.collide(q, off * 0.7, 0.006) for q in Pp[1:]])
            tl = [tiles_top[k] for k in ((0, 1, 2, 3) if li == 0 else (2, 3, 4, 5, 6, 7) if li == 1 else (6, 7, 8, 9, 10, 11))]
            b.card(Pp, rng.uniform(0.0075, 0.0105), rng.uniform(0.0016, 0.0026), int(rng.choice(tl)), jitter=0.08,
                   twist=rng.normal(0, 0.08))
    # ---------------- sides and back (not on the shaved side): short layered cards lying down/back
    zone = cm & (el > R_(-10)) & ~((el > R_(24)) | ((np.abs(az) < R_(55)) & (el > R_(14))))
    roots, rn = H.sample_roots(zone, 150, 0.0072, seed=77)
    F0 = flow(roots)
    for p, nn, f in zip(roots, rn, F0):
        a_, e_, _ = H.angles(p[None])
        if float(shaved(p[None], a_, e_, H)[0]) > 0.2:
            continue
        dd = float(dens(a_, e_, p[None])[0])
        if dd < 0.3:
            continue
        L = (0.01 + 0.042 * dd ** 1.5) * rng.uniform(0.85, 1.15)
        Pp = grow(H, p, nn, L, f, 7, 0.05, 1.0, 0.1, 0.0022, 1.2, 0.0, None, 0.0, 0.0, clear=0.0018, body_clear=0.004)
        if len(Pp) >= 3:
            b.card(Pp, rng.uniform(0.0055, 0.007), 0.0018, int(rng.choice(tiles_side)), jitter=0.12)
    roots, rn = H.sample_roots(cm & (el > R_(35)), 1, 0.03, seed=5)
    for p, nn in zip(roots, rn):
        d0 = flow(p[None])[0] + H.radial(p[None])[0] * 0.3
        Pp = grow(H, p, nn, rng.uniform(0.035, 0.065), d0, 6, 0.22, 1.2, 0.12, 0.010, 0.0, 0.0, None, 0.0, 0.0, clear=0.008, body_clear=0.01)
        if len(Pp) >= 3:
            b.card(Pp, 0.004, 0.001, int(rng.choice(wisp)))

    def hl_dir(p, a):
        sd = (-1.0 if p[0] < PART_X else 1.0) * ss(0.004, 0.012, abs(p[0] - PART_X))
        fa = ss(50, 80, abs(math.degrees(a)))
        d = np.array((sd * 0.45, 0.85, 0.75)) * (1 - fa) + np.array((math.copysign(0.2, p[0]), 0.8, -0.7)) * fa
        return H.tangent(p[None], d[None])[0]

    def hl_guard(q, p):
        a_, e_, _ = H.angles(q[None])
        return None if float(shaved(q[None], a_, e_, H)[0]) > 0.3 else q
    b.hairline_cards(hairline, hl_dir, fringe_t, az_max=78.0, step_deg=1.4, L=(0.022, 0.04), w=(0.005, 0.0068), off=0.0014,
                     guard=hl_guard, segs=6, rows=2, tiles_dense=fringe_t + [3, 4, 5], row_step=2.4)
    img = np.zeros((HV.ATLAS, HV.ATLAS, 4), np.float32)
    tv = [0.62, 0.7, 0.78, 0.86, 0.92, 1.0, 0.82, 0.9, 0.96, 1.02, 1.08, 1.12]
    specs = ([dict(v5=True, wave=0.06, tip_min=0.35, converge=0.5, value=tv[k], per=30, under=70, cw=(0.1, 0.2), root_dark=0.3)
              for k in range(12)] +
             [dict(v5=True, wave=0.0, tip_min=0.3, converge=0.4, value=v, per=28, under=60, root_dark=0.25)
              for v in (0.6, 0.68, 0.76, 0.84, 0.9, 0.96, 0.72, 0.8)] +
             [dict(n=8, wave=0.2, clumps=(1, 2), spread=0.15, tip_min=0.6, sparse=True, width=(0.9, 1.3))] * 2 +
             [dict(v5=True, wave=0.05, clumps=(5, 8), per=9, under=14, cw=(0.06, 0.12), cval=(0.75, 1.0), tip_min=0.35,
                   width=(0.9, 1.3), root_dark=0.12, root_stagger=0.32, converge=0.2, edge_fade=0.25)] * 2)
    HV.paint_atlas_tiles(img, specs, rng)
    partf = lambda P, el_: np.where((el_ > R_(26)) & (P[:, 1] < H.hc[1] + 0.02), P[:, 0] - PART_X, 1.0)
    HV.paint_cap(H, vol, img, flow, dens, partf, [k + (2.6 if i < 4 else 1.6) for i, k in enumerate(hairline)], soft=4.0, band_el=None,
                 stroke=(0.008, 0.02), lum_mul=0.7, part_cut=False)
    return vol, HV.finish(img, 0.8)


def main():
    rig = bpy.data.objects["Kael"]
    body = bpy.data.objects.get("BodyFull") or bpy.data.objects["Body"]
    for o in list(bpy.data.objects):
        if o.type == "MESH" and (o.name.startswith("Hair_") or o.name.startswith("Facial_")):
            bpy.data.objects.remove(o, do_unlink=True)
    ctx = gear.Ctx(body, rig, "Kael")
    for n in ("Top", "Collar", "Jacket", "ChestRig", "PauldronL", "PauldronR", "PauldronLameL", "PauldronLameR"):
        o = bpy.data.objects.get(n)
        if o is not None:
            HL.orient_outward(o, ctx)
            ctx.push_stack(o)
    H = Head(ctx, female=False)
    C.log("head", H.hc.round(4), "top", round(H.top, 4), "face_hw", round(H.face_hw, 4))
    t0 = time.time()
    b = HV.V4(H, ctx, "kael", STYLE)
    vol, atlas = build(b)
    cards = b.part.build(mat_order=["Hair"], max_edge=None)
    obj = gear.join([vol, cards], "Hair_" + STYLE)
    for p in obj.data.polygons:
        p.use_smooth = True
    HV.env_normals(obj, H)
    tex = os.path.join(KROOT, "tex", f"Hair_{STYLE}_Color.png")
    C.write_png(atlas, tex, "RGBA")
    C.log(STYLE, "tris", C.tris(obj), "cards", b.ncards, "s", round(time.time() - t0, 1))
    obj.data.name = obj.name
    bpy.data.libraries.write(os.path.join(KROOT, "blends", "hair_k3.blend"), {obj}, fake_user=True, compress=True)
    json.dump({"style": STYLE, "cutoff": b.cutoff, "tris": C.tris(obj), "part_x": PART_X},
              open(os.path.join(KROOT, "logs", "hair_k3.json"), "w"), indent=1)
    C.log("done")


if __name__ == "__main__":
    main()
