"""Procedural card beards (replace the removed MakeHuman community beard).

  style "scruffy" (Kael's optional beard): short 5-12 mm growth that reads well with stubble
  style "full"    (Oren): fuller 10-24 mm grey beard and moustache

Construction: a thin inner shell over the beard zone (dense short-hair texture, so no bald gaps) plus a few hundred
short tapered hair cards that grow along a facial flow field (down the jaw and chin, forward-down on the cheeks,
outward-down on the moustache), lie close to the skin and carry custom normals that follow the face surface.
Texture is drawn procedurally (strand tiles + shell texture, neutral grey; Unity tints it with the hair colour).
"""
import math
import numpy as np
import bpy
from mathutils import Vector
import gear
from gear import Part, nrm, ss
import texbake as TB
import hair_hd
import skin_hd

STYLES = {
    "scruffy": {"n": 900, "len": (0.005, 0.012), "width": (0.0034, 0.0022), "lift": 0.28, "shell": 0.0012, "min_d": 0.0019, "cheek_top": 0.034},
    "full": {"n": 1250, "len": (0.011, 0.024), "width": (0.0046, 0.003), "lift": 0.34, "shell": 0.0022, "min_d": 0.0017, "cheek_top": 0.03},
}


def beard_field(ctx, P, FL, cheek_top):
    """0..1 beard density at points P (rest pose)."""
    em, mouth, chin = FL["eyeM"], FL["mouth"], FL["chin"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    # upper boundary: low on the front of the cheeks, rising to the sideburns in front of the ears
    top = em[2] - cheek_top - 0.012 * ss(0.03, 0.0, ax) + 0.04 * ss(0.045, 0.072, ax)
    w = ss(0.0, 0.006, top - z)
    # stop in front of the ear / behind the jaw corner; keep the neck front under the jaw
    w *= 1 - ss(em[1] + 0.055, em[1] + 0.075, y)
    w *= ss(chin[2] - 0.075, chin[2] - 0.045, z)
    # lips: bare (vermilion) zone
    lip = ((x / 0.026) ** 2 + ((z - mouth[2]) / 0.0105) ** 2) < 1.0
    w = np.where(lip & (y < mouth[1] + 0.012), 0.0, w)
    # nose and the front of the cheeks above the moustache line
    nose = (ax < 0.03) & (z > mouth[2] + 0.021) & (y < em[1])
    w = np.where(nose, 0.0, w)
    # soft gap below the lower lip centre (soul patch keeps a few hairs)
    under = np.exp(-((x / 0.012) ** 2 + ((z - (mouth[2] - 0.016)) / 0.006) ** 2))
    w *= 1 - 0.5 * under
    # neck: thin out towards the bottom
    w *= 1 - 0.6 * ss(chin[2] - 0.02, chin[2] - 0.06, z)
    return np.clip(w, 0, 1)


def flow(P, N, FL):
    """Growth direction (tangent) per point."""
    em, mouth, chin = FL["eyeM"], FL["mouth"], FL["chin"]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    d = np.tile(np.array((0.0, 0.0, -1.0)), (len(P), 1))
    # cheeks: forward-down; moustache: outward-down; chin: down and slightly forward; neck: down-back
    d[:, 1] += np.where(y > mouth[1] + 0.02, -0.55, 0.0)
    must = (np.abs(x) < 0.03) & (z > mouth[2]) & (z < mouth[2] + 0.024)
    d[must, 0] = np.sign(x[must]) * 0.8
    d[must, 2] = -0.6
    neck = z < chin[2] - 0.015
    d[neck, 1] = 0.35
    d -= N * (d * N).sum(1, keepdims=True)
    return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)


def build_beard(ctx, name, out_tex, style="scruffy", seed=7, mat="Facial_beard"):
    S = STYLES[style]
    rng = np.random.default_rng(seed)
    FL = skin_hd.face_landmarks(ctx)
    co, vn = ctx.basis, ctx.vn
    region = (ctx.region["head"] + ctx.region["neck"]) > 0.4
    w = beard_field(ctx, co, FL, S["cheek_top"]) * region
    vmask = w > 0.02
    hc = np.array((0.0, FL["eyeM"][1] + 0.06, FL["eyeM"][2] - 0.04))
    # ---- inner shell (top half of the atlas: shell texture)
    shell = gear.shell(ctx, name + "_shell", vmask, lambda P, N: np.full(len(P), S["shell"]), mats=(mat,), smooth=1, subdiv=0, rim=0.0,
                       stack=False, cover=False, bsmooth=4, min_clear=S["shell"] * 0.7)
    hair_hd.set_cyl_uv(shell, hc)
    me = shell.data
    uv = me.uv_layers.active.data
    for l in uv:
        l.uv = (l.uv[0], 0.5 + 0.5 * l.uv[1])
    bw = beard_field(ctx, gear.get_co(shell), FL, S["cheek_top"])
    gear.set_attr(shell, "hairvol", np.ones(len(me.vertices)))
    gear.set_attr(shell, "bw", bw)
    # ---- cards (bottom half: 8 strand tiles)
    roots = hair_hd.sample_roots(ctx, vmask, S["n"], S["min_d"], seed)
    part = Part(name + "_cards")
    tree = ctx.tree
    rw = beard_field(ctx, roots, FL, S["cheek_top"])
    keep = rng.random(len(roots)) < (0.25 + 0.75 * rw)
    roots = roots[keep]
    rw = rw[keep]
    RN = np.array([np.array(tree.find_nearest(Vector(p), 0.05)[1] or Vector((0, -1, 0))) for p in roots])
    D = flow(roots, RN, FL)
    for p, n, d, wv in zip(roots, RN, D, rw):
        L = rng.uniform(*S["len"]) * (0.55 + 0.45 * wv)
        if p[2] < FL["chin"][2] + 0.01 and abs(p[0]) < 0.03:
            L *= 1.25                                    # a little longer on the chin
        d = nrm(d + rng.normal(0, 0.18, 3) - n * 0.0)
        lift = S["lift"] * rng.uniform(0.6, 1.2)
        c1 = p + n * 0.0005 + (d * math.cos(lift) + n * math.sin(lift)) * L * 0.55
        c2 = c1 + (d * math.cos(lift * 0.3) + n * math.sin(lift * 0.3) * 0.5 + rng.normal(0, 0.15, 3) * 0.3) * L * 0.5
        P = np.array([p - n * 0.0005, c1, c2])
        side = np.cross(d, n)
        side = side / max(np.linalg.norm(side), 1e-9)
        side = nrm(side + n * rng.uniform(-0.4, 0.4))
        wdt = rng.uniform(*sorted(S["width"]))
        col = rng.integers(0, 8)
        hair_hd.card_strip(part, P, np.array([side] * 3), np.array([wdt, wdt * 0.9, wdt * 0.6]), col * 0.125 + 0.006, col * 0.125 + 0.119, mat,
                           vrange=(0.0, 0.49), attrs={"lnx": np.full(6, n[0]), "lny": np.full(6, n[1]), "lnz": np.full(6, n[2])})
    cards = part.build(max_edge=None)
    obj = gear.join([shell, cards], name)
    hair_hd.volume_normals(obj, hc, card_mix=0.85, squash=(1.0, 1.0, 1.0))
    # ---- texture
    size = 1024
    lum = np.zeros((size, size), np.float32); alpha = np.zeros((size, size), np.float32)
    T = TB.raster([obj], mat, size, attrs=("hairvol", "bw"))
    idx = np.where(T.cov & (T.A["hairvol"][:] > 0.5))[0]
    Pt = T.P[idx].astype(np.float64)
    Nt = T.N[idx].astype(np.float64)
    bwt = T.A["bw"][idx]
    d = flow(Pt, Nt, FL)
    sd = np.cross(d, Nt)
    sd /= np.maximum(np.linalg.norm(sd, axis=1, keepdims=True), 1e-9)
    along = (Pt * d).sum(1)
    across = (Pt * sd).sum(1) + 0.0004 * TB.vnoise3(Pt, 900.0, 2.0)
    lane = np.floor(across / 0.0006)
    seg = np.floor(along / 0.0045 + TB.hash3(np.stack([lane, lane * 0 + 1, lane * 0], -1), 4.0) * 3)
    present = TB.hash3(np.stack([lane, seg, seg * 0 + 2], -1), 6.0)
    stroke = 0.5 + 0.5 * np.cos((across / 0.0006 - lane - 0.5) * 2 * math.pi)
    dens = 0.25 + 0.7 * bwt
    a_sh = np.clip((present < dens).astype(np.float32) * ss(0.25, 0.6, stroke) + ss(0.55, 0.95, bwt) * 0.85, 0, 1)
    l_sh = 0.2 + 0.6 * stroke * (0.6 + 0.4 * TB.hash3(np.stack([lane, seg, seg * 0], -1), 8.0))
    flat_l = np.zeros(size * size, np.float32); flat_l[idx] = l_sh
    flat_a = np.zeros(size * size, np.float32); flat_a[idx] = a_sh
    top = slice(size // 2, size)
    lum[top] = flat_l.reshape(size, size)[top]; alpha[top] = flat_a.reshape(size, size)[top]
    H_ = size // 2 - 8
    for k in range(8):
        cl, ca, _ = hair_hd.draw_strands(128, H_, 70, rng, curl=0.35 if style == "full" else 0.25, width=(1.2, 2.2), taper=0.65,
                                         root_dark=0.3, sheen=(0.5, 0.1), frizz=0.5)
        lum[4:4 + H_, k * 128:(k + 1) * 128] = np.where(ca > 0.1, 0.3 + 0.7 * cl, 0.3)
        alpha[4:4 + H_, k * 128:(k + 1) * 128] = ca
    img = hair_hd._hair_rgba(lum, alpha, (0.33, 0.33, 0.33))
    fn = "Facial_beard_Color.png"
    TB.write_png(img, out_tex + "/" + fn, "RGBA")
    return obj, fn
