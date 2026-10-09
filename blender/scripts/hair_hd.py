"""Procedural hero hair: `curly` (Kael default) and `wavy` (Giva/Lyra default).

Both styles are alpha-tested hair cards over a solid inner volume (so the head never reads as a cap):
  curly - a sculpted volume (thick on top, faded sides and nape) carrying a curly-mat texture, plus a few hundred
          coiled lock ribbons (twisted helical strips) rooted in it.
  wavy  - shoulder-length layered cards that fall with gravity and collide with the head, neck and clothing,
          shaped into S-waves with separated clumps, over a thin inner volume.
Textures are drawn procedurally (no image generation): strands are anti-aliased curves with per-strand value
variation, darker roots, a soft sheen band and tapered tips. The dye mask (tips) is stored in the texture's
blue-channel variant <style>_Dye.png for an optional tint in Unity.
"""
import math
import numpy as np
import bmesh
import bpy
from mathutils import Vector
import gear
from gear import Part, nrm, ss, tube
import texbake as TB


# ----------------------------------------------------------------------------- scalp


def head_frame(ctx):
    L = ctx.L
    eye = (L["LeftEye"] + L["RightEye"]) * 0.5
    top = ctx.T["Head"]
    hc = np.array((0.0, eye[1] + 0.085, eye[2] + 0.02))
    return hc, eye, top


def scalp_mask(ctx, hairline="male"):
    hc, eye, top = head_frame(ctx)
    co = ctx.basis
    d = co - hc
    r = np.linalg.norm(d, axis=1)
    az = np.abs(np.arctan2(d[:, 0], -d[:, 1]))  # 0 front, pi back
    el = np.arcsin(np.clip(d[:, 2] / np.maximum(r, 1e-6), -1, 1))
    deg = np.degrees
    # minimum elevation of the hairline as a function of azimuth
    knots_az = np.radians([0, 30, 55, 80, 100, 125, 150, 180])
    if hairline == "male":
        knots_el = np.radians([18, 17, 13, 8, 2, -14, -30, -36])
    else:
        knots_el = np.radians([27, 25, 15, 6, -2, -18, -34, -40])
    el_min = np.interp(az, knots_az, knots_el)
    head = ctx.region["head"] > 0.5
    ears = (np.abs(d[:, 0]) > 0.06) & (el < np.radians(12)) & (az > np.radians(70)) & (az < np.radians(115))
    m = head & (el > el_min) & ~ears
    return m, az, el, r


def sample_roots(ctx, mask, n, min_d, seed=0):
    """Area-weighted random points on body faces whose verts are all in mask, with a minimum spacing."""
    B = ctx.B
    co = ctx.basis
    fids = [i for i, f in enumerate(B.faces) if all(mask[v] for v in f)]
    tri = []
    for fi in fids:
        f = B.faces[fi]
        for k in range(1, len(f) - 1):
            tri.append((f[0], f[k], f[k + 1]))
    tri = np.array(tri)
    A = np.linalg.norm(np.cross(co[tri[:, 1]] - co[tri[:, 0]], co[tri[:, 2]] - co[tri[:, 0]]), axis=1) * 0.5
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(tri), size=n * 6, p=A / A.sum())
    u = rng.random((n * 6, 2))
    flip = u.sum(1) > 1
    u[flip] = 1 - u[flip]
    P = co[tri[pick, 0]] * (1 - u[:, :1] - u[:, 1:]) + co[tri[pick, 1]] * u[:, :1] + co[tri[pick, 2]] * u[:, 1:]
    out = []
    for p in P:
        if all(np.linalg.norm(p - q) >= min_d for q in out[-400:]):
            out.append(p)
        if len(out) >= n:
            break
    return np.array(out)


# ----------------------------------------------------------------------------- strand textures


def draw_strands(W, H, n, rng, curl=0.0, wave=0.0, width=(0.6, 1.4), taper=0.25, root_dark=0.35, sheen=(0.45, 0.12),
                 frizz=0.0, dense_root=True):
    """Draw n strands running along v (root at v=1, tip at v=0) into a W x H tile. Returns (lum, alpha, tipmask).
    Vectorised per strand over all rows."""
    lum = np.zeros((H, W), np.float32)
    alpha = np.zeros((H, W), np.float32)
    v = 1 - (np.arange(H) + 0.5) / H  # 1 root .. 0 tip
    xs = np.arange(W)[None, :]
    for _ in range(n):
        x0 = rng.uniform(0.05, 0.95) * W
        ln = rng.uniform(0.55, 1.0)
        ph = rng.uniform(0, 2 * math.pi)
        amp = W * (0.02 + curl * rng.uniform(0.05, 0.12))
        freq = 2 + curl * rng.uniform(5, 9) + wave * rng.uniform(1.2, 2.0)
        cx = x0 + amp * np.sin(v * freq * 2 * math.pi + ph) + W * frizz * rng.normal(0, 1) * (1 - v) * 0.05
        cx = cx + W * 0.15 * wave * np.sin(v * 3.1 + ph) * (1 - v)
        w = rng.uniform(*width) * (1 - taper * (1 - v))
        tipfade = ss(1 - ln, 1 - ln + 0.12, v)
        a = np.clip(1.0 - (np.abs(xs - cx[:, None]) - w[:, None] * 0.5), 0, 1) * tipfade[:, None]
        brightness = rng.uniform(0.55, 1.0)
        l = brightness * (1 - root_dark * ss(0.75, 1.0, v)) * (1 + sheen[1] * np.exp(-((v - sheen[0]) / 0.08) ** 2) * 2.0)
        upd = a > 0.3
        lum = np.where(upd, np.maximum(lum, l[:, None]), lum)
        alpha = np.maximum(alpha, a)
    tip = 1 - v
    return lum, alpha, np.repeat(tip[:, None], W, 1)


def curly_mat_tile(W, H, rng, n=1400):
    """Dense curly mat (for the inner volume): many small arcs; alpha mostly solid."""
    lum = np.full((H, W), 0.35, np.float32)
    alpha = np.full((H, W), 1.0, np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    for _ in range(n):
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(3, 9) * W / 512
        a0 = rng.uniform(0, 2 * math.pi)
        sweep = rng.uniform(2.5, 5.5)
        x0, x1 = int(max(cx - r - 2, 0)), int(min(cx + r + 3, W))
        y0, y1 = int(max(cy - r - 2, 0)), int(min(cy + r + 3, H))
        if x1 <= x0 or y1 <= y0:
            continue
        X, Y = xx[y0:y1, x0:x1] - cx, yy[y0:y1, x0:x1] - cy
        d = np.abs(np.hypot(X, Y) - r)
        ang = (np.arctan2(Y, X) - a0) % (2 * math.pi)
        on = (ang < sweep) & (d < 1.1)
        b = rng.uniform(0.5, 1.0) * (0.75 + 0.25 * np.sin(ang * 1.5))
        lum[y0:y1, x0:x1] = np.where(on, np.maximum(lum[y0:y1, x0:x1], b), lum[y0:y1, x0:x1])
    return lum, alpha


def coil_tile(W, H, rng, n=40):
    return draw_strands(W, H, n, rng, curl=1.0, width=(1.0, 2.0), taper=0.4, root_dark=0.3, sheen=(0.5, 0.15), frizz=0.6)


# ----------------------------------------------------------------------------- geometry helpers


def card_strip(part, P, side, width, u0, u1, mat, attrs=None, flip_uv=False, vrange=(0.0, 1.0)):
    """Ribbon card along points P (root first) spanning +-side*width/2. UV: u across [u0,u1], v from 1 (root) to 0."""
    n = len(P)
    verts, faces, uvs = [], [], []
    for i in range(n):
        w = width[i] if hasattr(width, "__len__") else width
        verts += [P[i] - side[i] * w * 0.5, P[i] + side[i] * w * 0.5]
    for i in range(n - 1):
        a = i * 2
        faces.append([a, a + 2, a + 3, a + 1])
        v0, v1 = 1 - i / (n - 1), 1 - (i + 1) / (n - 1)
        v0 = vrange[0] + (vrange[1] - vrange[0]) * v0
        v1 = vrange[0] + (vrange[1] - vrange[0]) * v1
        uvs.append([(u0, v0), (u0, v1), (u1, v1), (u1, v0)])
    part.add(np.array(verts), faces, mat, uvs, attrs)


def volume_normals(obj, hc, card_mix=0.25, squash=(1.0, 1.0, 1.15)):
    """Hair-card shading trick: card vertices get normals pointing away from the head volume (an ellipsoid around
    hc), lightly mixed with their own normal; the solid volume keeps its smooth normals. Exported as custom split
    normals (Unity imports them), so the cards shade like a continuous mass of hair instead of flat sheets."""
    me = obj.data
    me.update()
    co = gear.get_co(obj)
    vn = gear.vnormals(obj)
    hv = gear.attr(obj, "hairvol")
    d = (co - hc) / np.array(squash)
    sph = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    sgn = np.sign((vn * sph).sum(1, keepdims=True))
    sgn[sgn == 0] = 1
    cardn = vn * sgn
    ln = np.stack([gear.attr(obj, "lnx"), gear.attr(obj, "lny"), gear.attr(obj, "lnz")], 1)
    has = np.linalg.norm(ln, axis=1) > 0.5
    cardn[has] = ln[has]
    n = np.where(hv[:, None] > 0.5, vn, sph * (1 - card_mix) + cardn * card_mix)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    me.normals_split_custom_set_from_vertices([tuple(v) for v in n])


def collide(ctx, P, clear, tree):
    out = P.copy()
    for i in range(1, len(out)):
        hit, hn, _, _ = tree.find_nearest(Vector(out[i]), 0.3)
        if hit is None:
            continue
        g = (Vector(out[i]) - hit).dot(hn)
        if g < clear:
            out[i] = np.array(hit + hn * clear)
    return out


# ----------------------------------------------------------------------------- styles


def sph_uv(P, hc, rect, el_range=(-50.0, 90.0)):
    """Spherical (azimuth, elevation) UVs around the head centre, mapped into rect=(u0, v0, u1, v1)."""
    d = P - hc
    az = np.arctan2(d[:, 0], -d[:, 1])  # -pi..pi, 0 = front
    el = np.degrees(np.arcsin(np.clip(d[:, 2] / np.maximum(np.linalg.norm(d, axis=1), 1e-9), -1, 1)))
    u = (az + math.pi) / (2 * math.pi)
    v = (el - el_range[0]) / (el_range[1] - el_range[0])
    u0, v0, u1, v1 = rect
    return np.stack([u0 + (u1 - u0) * u, v0 + (v1 - v0) * np.clip(v, 0, 1)], 1)


def set_sph_uv(obj, hc, rect, el_range=(-50.0, 90.0)):
    me = obj.data
    co = gear.get_co(obj)
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active.data
    # per-loop UVs; fix the azimuth seam per face so no face wraps around the texture
    for p in me.polygons:
        lis = list(p.loop_indices)
        P = co[[me.loops[li].vertex_index for li in lis]]
        uv = sph_uv(P, hc, rect, el_range)
        du = rect[2] - rect[0]
        if uv[:, 0].max() - uv[:, 0].min() > du * 0.5:
            uv[:, 0] = np.where(uv[:, 0] > rect[0] + du * 0.5, uv[:, 0] - du, uv[:, 0])  # texture repeats in u
        for k, li in enumerate(lis):
            uvl[li].uv = tuple(uv[k])


def fade_mat_tile(W, H, rng, el_range, fade_el=(5.0, 24.0), n_arcs=5200):
    """Volume texture painted in (azimuth, elevation) space: stubble fade at the sides blending into a dense
    curly mat on top. Periodic in u."""
    yy, xx = np.mgrid[0:H, 0:W]
    el = el_range[0] + (yy + 0.5) / H * (el_range[1] - el_range[0])
    top = ss(fade_el[0], fade_el[1], el)
    lum = np.full((H, W), 0.22, np.float32)
    # curly arcs (wrap horizontally)
    for _ in range(n_arcs):
        cy = rng.uniform(0, H)
        if rng.random() > ss(fade_el[0] - 6, fade_el[1], el_range[0] + cy / H * (el_range[1] - el_range[0])) + 0.05:
            continue
        cx = rng.uniform(0, W)
        r = rng.uniform(2.0, 5.5) * W / 512
        a0 = rng.uniform(0, 2 * math.pi); sweep = rng.uniform(2.8, 5.8)
        x0, x1 = int(cx - r - 2), int(cx + r + 3)
        y0, y1 = int(max(cy - r - 2, 0)), int(min(cy + r + 3, H))
        if y1 <= y0:
            continue
        xs = np.arange(x0, x1) % W
        X = np.arange(x0, x1)[None, :] - cx
        Y = np.arange(y0, y1)[:, None] - cy
        d = np.abs(np.hypot(X, Y) - r)
        ang = (np.arctan2(Y, X) - a0) % (2 * math.pi)
        on = np.clip(1.1 - d, 0, 1) * (ang < sweep)
        b = rng.uniform(0.4, 0.85) * (0.75 + 0.25 * np.sin(ang * 1.3))
        sub = lum[y0:y1][:, xs]
        lum[y0:y1, xs] = np.maximum(sub, on * b)
    # stubble dots on the faded sides
    dots = (rng.random((H, W)) < 0.22).astype(np.float32) * rng.uniform(0.3, 0.7, (H, W))
    side = 1 - top
    lum = np.where(top > 0.5, lum, np.maximum(lum * top * 2, dots * 0.8))
    alpha = np.clip(top * 1.2 + side * (0.35 + 0.65 * (dots > 0)) * ss(el_range[0], fade_el[0], el) * 0.0 + side * (dots > 0) * 0.9, 0, 1)
    alpha = np.maximum(alpha, top)
    return lum, alpha


def worley_vec(P, freq, seed=0.0):
    """F1 distance (cell units) and the nearest feature point (metres) for 3D points."""
    P = np.asarray(P, np.float64)
    Q = P * freq
    i = np.floor(Q)
    best = np.full(len(Q), 9.0); fp_best = np.zeros_like(Q)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                g = i + np.array((dx, dy, dz))
                fp = g + np.stack([TB.hash3(g, seed), TB.hash3(g, seed + 1.3), TB.hash3(g, seed + 2.7)], -1)
                d = np.linalg.norm(Q - fp, axis=1)
                m = d < best
                best = np.where(m, d, best)
                fp_best = np.where(m[:, None], fp, fp_best)
    return best, fp_best / freq


CURL_F = 68.0   # clump frequency (1/m): ~1.5 cm curl clusters


def _curl_fields(bp, hgt_rel, normal):
    """Shared by geometry and texture: dome height 0..1, crevice 0..1 and spiral strand pattern 0..1."""
    F1, fp = worley_vec(bp, CURL_F, 2.0)
    dome = np.clip(1 - F1 / 0.78, 0, 1) ** 1.4
    crev = ss(0.5, 0.85, F1)
    v = bp - fp
    v = v - normal * (v * normal).sum(1, keepdims=True)
    r = np.linalg.norm(v, axis=1)
    t1 = np.cross(normal, np.array((0.0, 0.0, 1.0)))
    t1 /= np.maximum(np.linalg.norm(t1, axis=1, keepdims=True), 1e-9)
    t2 = np.cross(normal, t1)
    ang = np.arctan2((v * t2).sum(1), (v * t1).sum(1))
    spiral = 0.5 + 0.5 * np.cos(2 * math.pi * r / 0.0017 + ang * 2 + TB.hash3(fp, 5.0) * 6.28)
    return dome * hgt_rel, crev * hgt_rel, spiral


def _flow_dir(p, hc, style, part_x, rng):
    """Initial growth direction (tangent to the scalp) for a root at p."""
    d = p - hc
    out = nrm(d)
    az = math.degrees(math.atan2(d[0], -d[1]))       # 0 front, +90 character left
    el = math.degrees(math.asin(max(-1, min(1, d[2] / np.linalg.norm(d)))))
    if style == "curly":
        if abs(az) < 50 and el > 18:
            f = np.array((rng.normal(0, 0.5), -0.9, 0.35))          # tumble forward over the forehead
        elif el > 45:
            f = np.array((math.copysign(0.5, d[0] + rng.normal(0, 0.02)), 0.2 * rng.normal(), 0.2))
        else:
            f = np.array((d[0] * 3, 0.4 if d[1] > 0 else -0.1, -1.0))
    else:
        side = 1.0 if p[0] > part_x else -1.0
        if d[1] < -0.045 and el > 10:
            f = np.array((side * 0.7, 0.8, 0.15))                    # swept back off the face from the part
        else:
            f = np.array((side * (0.9 if el > 35 else 0.35), 0.35 if d[1] > -0.02 else 0.0, -0.6))
    f = f + rng.normal(0, 0.12, 3)
    f = f - out * (f @ out)
    return nrm(f)


def lock_hair(ctx, name, mat, out_tex, style, seed=3):
    """Lock-card hair: an inner solid volume plus layered ribbon locks that grow along a flow field, hug the scalp,
    fall with gravity, collide with head/neck/clothing and are shaped into helical ringlets (curly) or waves."""
    rng = np.random.default_rng(seed)
    hc, eye, top = head_frame(ctx)
    curly = style == "curly"
    mask, az, el, r = scalp_mask(ctx, "male" if curly else "female")
    EL = (-60.0, 90.0)
    part_x = 0.03

    def thick(P, N):
        d = P - hc
        rr = np.linalg.norm(d, axis=1)
        e = np.arcsin(np.clip(d[:, 2] / rr, -1, 1))
        if curly:
            return 0.003 + 0.016 * ss(np.radians(0), np.radians(35), e)
        return 0.004 + 0.009 * ss(np.radians(-10), np.radians(40), e)

    vol = gear.shell(ctx, name + "_vol", mask, thick, mats=(mat,), smooth=6, subdiv=1, rim=0.0, stack=False, cover=False,
                     bsmooth=14, min_clear=0.0015)
    if curly:
        pv = gear.get_co(vol); nv = gear.vnormals(vol)
        bp = np.stack([gear.attr(vol, "bx"), gear.attr(vol, "by"), gear.attr(vol, "bz")], 1)
        F1, _ = worley_vec(bp, 70.0, 2.0)
        gear.set_co(vol, pv + nv * (0.004 * np.clip(1 - F1 / 0.8, 0, 1))[:, None])
    set_sph_uv(vol, hc, (0.0, 0.5, 1.0, 1.0), EL)
    gear.set_attr(vol, "hairvol", np.ones(len(vol.data.vertices)))
    tree = ctx.outer_tree()
    part = Part(name + "_locks")
    if curly:
        layers = [(80, 0.007, 0.0, 1.0), (70, 0.014, 0.0, 1.0), (28, 0.02, 20.0, 0.9)]
    else:
        layers = [(150, 0.005, -40.0, 1.0), (200, 0.009, -40.0, 1.0), (110, 0.013, 0.0, 0.92), (40, 0.016, 25.0, 0.8)]
    for li, (n, off, el_min, lmul) in enumerate(layers):
        roots = sample_roots(ctx, mask & (el > np.radians(el_min)), n, 0.016 if curly else 0.0095, seed + li * 13)
        for p in roots:
            d = p - hc
            out = nrm(d)
            a_ = math.degrees(math.atan2(d[0], -d[1])); e_ = math.degrees(math.asin(max(-1, min(1, d[2] / np.linalg.norm(d)))))
            if curly:
                # medium: top/back to jaw or upper neck; tapered sides and nape; short forehead curls
                L_ = 0.17 if e_ > 30 else (0.13 if abs(a_) > 120 else 0.095)
                if abs(a_) < 50 and e_ > 18:
                    L_ = 0.10
                if abs(a_) > 140 and e_ < 0:
                    L_ = 0.055                       # tapered nape
                L_ *= rng.uniform(0.8, 1.12) * lmul
            else:
                L_ = 0.42 * rng.uniform(0.82, 1.08) * lmul       # past the shoulders, layered by lmul
                if d[1] < -0.04 and abs(d[0]) > 0.05 and e_ < 20:
                    L_ *= 0.75                       # face-framing layers
            flow = _flow_dir(p, hc, style, part_x, rng)
            segs = 26 if curly else 13
            step = L_ / segs
            P = [p + out * off]
            dirv = flow
            for i in range(segs):
                g = (0.1 if i < 3 else 0.32) if not curly else (0.06 if i < 2 else 0.22)
                dirv = nrm(dirv * (1 - g) + np.array((0, 0, -1.0)) * g)
                o_ = nrm(P[-1] - hc)
                if np.linalg.norm(P[-1] - hc) < 0.135:
                    dirv = nrm(dirv - o_ * max(0.0, dirv @ o_) * 0.85)     # hug the scalp
                q = P[-1] + dirv * step
                hit, hn, _, _ = tree.find_nearest(Vector(q), 0.3)
                if hit is not None:
                    gg = (Vector(q) - hit).dot(hn)
                    if gg < off + 0.005:
                        q = np.array(hit + hn * (off + 0.005))
                if not curly and q[1] < hc[1] - 0.03 and abs(q[0]) < 0.078 and q[2] < hc[2] + 0.03:
                    q[0] = math.copysign(0.078, q[0] if abs(q[0]) > 1e-4 else 1.0)   # never across the face
                if curly and q[1] < hc[1] - 0.07 and q[2] < eye[2] + 0.028:
                    q[2] = eye[2] + 0.028                                         # forehead curls stop above the brows
                dirv = nrm(q - P[-1])
                P.append(q)
            P = np.array(P)
            Nout = np.array([nrm(q - np.array((hc[0], hc[1] + 0.01, min(q[2], hc[2])))) for q in P])
            T_ = gear.tangents(P)
            S = np.cross(T_, Nout); S /= np.maximum(np.linalg.norm(S, axis=1, keepdims=True), 1e-9)
            Nn = np.cross(S, T_)
            arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
            sN = arc / max(arc[-1], 1e-6)
            ph = rng.uniform(0, 2 * math.pi)
            if curly:
                R_ = rng.uniform(0.009, 0.012) * ss(0.04, 0.25, sN) + 0.002
                pitch = rng.uniform(0.04, 0.05)
                th = 2 * math.pi * arc / pitch + ph
                radial = S * np.cos(th)[:, None] + Nn * np.sin(th)[:, None]
                P2 = P + radial * R_[:, None]
                side = T_                                   # ringlet band: width along the lock axis -> spiral column
                w = pitch * np.linspace(0.95, 0.55, segs + 1)
                lock_n = radial
            else:
                lam = rng.uniform(0.07, 0.09)
                amp = 0.013 * ss(0.12, 0.45, sN) * rng.uniform(0.7, 1.2)
                th = 2 * math.pi * arc / lam + ph
                curl_end = ss(0.55, 1.0, sN) * rng.uniform(0.004, 0.012)
                P2 = P + S * (amp * np.sin(th))[:, None] + Nn * (amp * 0.45 * np.cos(th) + curl_end * np.sin(th * 1.6))[:, None]
                side = S
                w = np.linspace(0.026, 0.012, segs + 1) * (1 + 0.15 * np.sin(sN * math.pi))
                lock_n = Nn
            P2 = collide(ctx, P2, off + 0.004, tree)
            col = rng.integers(0, 8)
            ln_ = np.repeat(lock_n, 2, axis=0)
            card_strip(part, P2, side, w, col * 0.125 + 0.003, col * 0.125 + 0.122, mat, vrange=(0.0, 0.49),
                       attrs={"lnx": ln_[:, 0], "lny": ln_[:, 1], "lnz": ln_[:, 2]})
    locks = part.build()
    obj = gear.join([vol, locks], name)
    volume_normals(obj, hc + np.array((0, 0.015, -0.02 if curly else -0.06)), card_mix=0.6 if curly else 0.55, squash=(1.0, 1.0, 1.15 if curly else 1.6))
    # textures: top half volume strands (flowing down in elevation), bottom half 8 lock tiles
    size = 1024
    lum = np.zeros((size, size), np.float32); alpha = np.zeros((size, size), np.float32); tip = np.zeros((size, size), np.float32)
    cl, ca, _ = draw_strands(size, size // 2, 1500, rng, curl=0.25 if curly else 0.0, wave=0.0 if curly else 0.5, width=(1.0, 2.0), taper=0.0,
                             root_dark=0.0, sheen=(0.7, 0.1))
    lum[size // 2:] = 0.1 + 0.75 * cl[::-1]; alpha[size // 2:] = 1.0
    H_ = size // 2 - 8
    for k in range(8):
        cl, ca, ct = draw_strands(128, H_, 260, rng, curl=0.18 if curly else 0.0, wave=0.0 if curly else 0.6, width=(0.9, 1.6), taper=0.55,
                                  root_dark=0.45, sheen=(0.5, 0.22))
        xs = np.abs(np.arange(128) - 63.5) / 64.0
        core = (1 - ss(0.25, 0.7, xs))[None, :] * ss(0.0, 0.25, np.linspace(1, 0, H_))[:, None]
        ca = np.clip(np.maximum(ca, core * 0.85), 0, 1)
        cl = np.where(cl > 0, 0.15 + 0.85 * cl, 0.04 + 0.06 * core)
        lum[4:4 + H_, k * 128:(k + 1) * 128] = cl
        alpha[4:4 + H_, k * 128:(k + 1) * 128] = ca
        tip[4:4 + H_, k * 128:(k + 1) * 128] = ss(0.65, 0.92, ct)
    img = _hair_rgba(lum, alpha, (0.20, 0.13, 0.09) if curly else (0.17, 0.11, 0.08))
    fn = f"Hair_{style}_Color.png"
    TB.write_png(img, out_tex + "/" + fn, "RGBA")
    if not curly:
        TB.write_png(np.stack([tip] * 3, -1), out_tex + "/Hair_wavy_Dye.png", "RGB")
    return obj, fn


def build_curly(ctx, name, out_tex, seed=3):
    return lock_hair(ctx, name, "Hair_curly", out_tex, "curly", seed)


def build_wavy(ctx, name, out_tex, seed=5):
    return lock_hair(ctx, name, "Hair_wavy", out_tex, "wavy", seed)


def hair_weights(obj, ctx, rig_bones=("Head", "Neck", "Spine2")):
    """Long-hair skinning without extra bones: Head above the ears, blending to Neck and Spine2 towards the
    shoulders, so locks below the jaw follow the torso instead of swinging through the shoulders."""
    co = gear.get_co(obj)
    L = ctx.L
    zj = L["Head"][2] - 0.01            # jaw level
    zs = L["LeftShoulder"][2] + 0.02    # shoulder level
    t = np.clip((zj - co[:, 2]) / max(zj - zs, 1e-3), 0, 1.5)
    wh = np.clip(1 - t * 0.75, 0.0, 1.0)
    ws = np.clip((t - 0.6) * 1.0, 0, 0.7)
    wn = np.clip(1 - wh - ws, 0, 1)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    for nm, w in (("Head", wh), ("Neck", wn), ("Spine2", ws)):
        vg = obj.vertex_groups.new(name="mixamorig:" + nm)
        for i in np.where(w > 0.01)[0]:
            vg.add([int(i)], float(w[i]), "REPLACE")


def _hair_rgba(lum, alpha, base_rgb):
    lum = np.clip(lum, 0, 1.4)
    rgb = np.stack([lum * base_rgb[0] * 2.4, lum * base_rgb[1] * 2.4, lum * base_rgb[2] * 2.4], -1)
    a = TB.dilate(np.concatenate([rgb, alpha[..., None]], -1), alpha > 0.05, 4)
    a[..., 3] = alpha
    return np.clip(a, 0, 1)


def _pack_volume_uvs(obj, mat, rect, part_attr=None):
    """Volume faces (smart-UV'd shell, attribute hairvol=1) are squeezed into rect=(u0, v0, u1, v1); card UVs stay."""
    me = obj.data
    uv = me.uv_layers.active.data
    hv = gear.attr(obj, "hairvol")
    u0, v0, u1, v1 = rect
    for p in me.polygons:
        if hv[p.vertices[0]] > 0.5:
            for li in p.loop_indices:
                x, y = uv[li].uv
                uv[li].uv = (u0 + (u1 - u0) * (x * 0.96 + 0.02), v0 + (v1 - v0) * (y * 0.96 + 0.02))


def improve_mh_hair(obj, src_png, out_png, hc, size=1024, seed=1):
    """Improve a MakeHuman hair card texture: crisper alpha for alpha-testing (cutoff ~0.4), strand contrast,
    3D-aware root darkening (near the scalp) and a soft baked anisotropic sheen band around the crown."""
    img = TB.read_image(src_png, size)
    rgb, a = img[..., :3], img[..., 3]
    lum = rgb.mean(-1)
    # strand contrast via local detail boost
    base = TB.blur(lum, 3)
    lum2 = np.clip(base + (lum - base) * 1.8, 0, 1)
    T = TB.raster([obj], obj.data.materials[0].name, size, attrs=())
    cov = T.cov.reshape(size, size)
    P = T.P.reshape(size, size, 3)
    d = P - hc
    r = np.linalg.norm(d, axis=-1) + 1e-6
    el = np.arcsin(np.clip(d[..., 2] / r, -1, 1))
    # distance from the head surface ~ r - head radius (0.095): roots darker
    rootk = np.clip(1 - ss(0.095, 0.125, r), 0, 1) * cov
    band = np.exp(-((el - np.radians(52)) / np.radians(9)) ** 2) * cov
    noise = TB.fbm3(np.stack([d[..., 0] * 30, d[..., 1] * 30, d[..., 2] * 30], -1).reshape(-1, 3), 1.0, 3, seed).reshape(size, size)
    lum3 = lum2 * (1 - 0.35 * rootk) * (1 + 0.28 * band * (0.6 + 0.4 * noise))
    a2 = ss(0.22, 0.62, a)
    out = np.concatenate([np.stack([lum3 * (rgb[..., c] / np.maximum(lum, 1e-3)) for c in range(3)], -1), a2[..., None]], -1)
    out[..., :3] = np.clip(out[..., :3], 0, 1)
    out = TB.dilate(out, a2 > 0.05, 4)
    out[..., 3] = a2
    TB.write_png(out, out_png, "RGBA")


def scalp_field(P, hc, hairline="male", soft=4.0):
    """Smooth 0..1 field that is 1 on the scalp above the hairline (for darkening the skin under hair)."""
    d = P - hc
    r = np.linalg.norm(d, axis=1) + 1e-9
    az = np.abs(np.arctan2(d[:, 0], -d[:, 1]))
    el = np.degrees(np.arcsin(np.clip(d[:, 2] / r, -1, 1)))
    knots_az = np.radians([0, 30, 55, 80, 100, 125, 150, 180])
    kn = [18, 17, 13, 8, 2, -14, -30, -36] if hairline == "male" else [27, 25, 15, 6, -2, -18, -34, -40]
    el_min = np.interp(az, knots_az, kn) + 10.0 * np.exp(-((np.degrees(az) - 92) / 14.0) ** 2)  # keep the ears clean
    return ss(el_min + 5.0, el_min + 5.0 + soft, el) * (r < 0.14)


# ============================================================================= sculpted lock hair (v8)


def lock_paths(ctx, style, seed=3):
    """Shaped lock centre-lines: list of (points (n,3), radii (n,), tangents (n,3))."""
    rng = np.random.default_rng(seed)
    hc, eye, top = head_frame(ctx)
    curly = style == "curly"
    mask, az, el, r = scalp_mask(ctx, "male" if curly else "female")
    tree = ctx.outer_tree()
    part_x = 0.03
    out_locks = []
    layers = ([(120, 0.004, 0.0, 1.0), (90, 0.012, 10.0, 1.0), (40, 0.02, 25.0, 0.9)] if curly else
              [(170, 0.004, -40.0, 1.0), (170, 0.010, -30.0, 1.0), (90, 0.016, 0.0, 0.92), (40, 0.02, 25.0, 0.82)])
    for li, (n, off, el_min, lmul) in enumerate(layers):
        roots = sample_roots(ctx, mask & (el > np.radians(el_min)), n, 0.013 if curly else 0.0105, seed + li * 13)
        for p in roots:
            d = p - hc
            out = nrm(d)
            a_ = math.degrees(math.atan2(d[0], -d[1])); e_ = math.degrees(math.asin(max(-1, min(1, d[2] / np.linalg.norm(d)))))
            if curly:
                L_ = 0.16 if e_ > 30 else (0.13 if abs(a_) > 120 else 0.09)
                if abs(a_) < 50 and e_ > 18:
                    L_ = 0.095
                if abs(a_) > 140 and e_ < 0:
                    L_ = 0.05
                L_ *= rng.uniform(0.85, 1.12) * lmul
                rad0 = rng.uniform(0.0065, 0.008)
            else:
                L_ = 0.42 * rng.uniform(0.85, 1.08) * lmul
                if d[1] < -0.04 and abs(d[0]) > 0.05 and e_ < 20:
                    L_ *= 0.72
                rad0 = rng.uniform(0.0075, 0.0095)
            flow = _flow_dir(p, hc, style, part_x, rng)
            segs = 30 if curly else 22
            step = L_ / segs
            P = [p + out * off]
            dirv = flow
            clear = off + rad0 * 0.8
            for i in range(segs):
                g = (0.1 if i < 3 else 0.32) if not curly else (0.05 if i < 2 else 0.2)
                dirv = nrm(dirv * (1 - g) + np.array((0, 0, -1.0)) * g)
                o_ = nrm(P[-1] - hc)
                if np.linalg.norm(P[-1] - hc) < 0.14:
                    dirv = nrm(dirv - o_ * max(0.0, dirv @ o_) * 0.85)
                q = P[-1] + dirv * step
                hit, hn, _, _ = tree.find_nearest(Vector(q), 0.3)
                if hit is not None:
                    gg = (Vector(q) - hit).dot(hn)
                    if gg < clear:
                        q = np.array(hit + hn * clear)
                if not curly and q[1] < hc[1] - 0.03 and abs(q[0]) < 0.08 and q[2] < hc[2] + 0.03:
                    q[0] = math.copysign(0.08, q[0] if abs(q[0]) > 1e-4 else 1.0)
                if curly and q[1] < hc[1] - 0.07 and q[2] < eye[2] + 0.03:
                    q[2] = eye[2] + 0.03
                dirv = nrm(q - P[-1])
                P.append(q)
            P = np.array(P)
            Nout = np.array([nrm(q - np.array((hc[0], hc[1] + 0.01, min(q[2], hc[2])))) for q in P])
            T_ = gear.tangents(P)
            S = np.cross(T_, Nout); S /= np.maximum(np.linalg.norm(S, axis=1, keepdims=True), 1e-9)
            Nn = np.cross(S, T_)
            arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
            sN = arc / max(arc[-1], 1e-6)
            ph = rng.uniform(0, 2 * math.pi)
            if curly:
                R_ = rng.uniform(0.007, 0.0105) * ss(0.05, 0.3, sN)
                pitch = rng.uniform(0.032, 0.042)
                th = 2 * math.pi * arc / pitch + ph
                P2 = P + (S * np.cos(th)[:, None] + Nn * np.sin(th)[:, None]) * R_[:, None]
                rad = rad0 * (1 - 0.45 * sN)
            else:
                lam = rng.uniform(0.075, 0.095)
                amp = 0.012 * ss(0.12, 0.45, sN) * rng.uniform(0.7, 1.2)
                th = 2 * math.pi * arc / lam + ph
                P2 = P + S * (amp * np.sin(th))[:, None] + Nn * (amp * 0.45 * np.cos(th))[:, None]
                rad = rad0 * (1 - 0.6 * sN ** 1.5)
            P2 = collide(ctx, P2, clear, tree)
            out_locks.append((P2, rad, gear.tangents(P2)))
    return out_locks, mask


def set_cyl_uv(obj, c):
    """Cylindrical UVs around a vertical axis through c: u = azimuth, v = height (texture repeats in u)."""
    me = obj.data
    co = gear.get_co(obj)
    z0, z1 = co[:, 2].min(), co[:, 2].max()
    uvl = me.uv_layers.active.data if me.uv_layers else me.uv_layers.new(name="UVMap").data
    for p in me.polygons:
        lis = list(p.loop_indices)
        P = co[[me.loops[li].vertex_index for li in lis]]
        u = (np.arctan2(P[:, 0] - c[0], -(P[:, 1] - c[1])) + math.pi) / (2 * math.pi)
        v = (P[:, 2] - z0) / max(z1 - z0, 1e-6)
        if u.max() - u.min() > 0.5:
            u = np.where(u > 0.5, u - 1.0, u)
        for k, li in enumerate(lis):
            uvl[li].uv = (float(u[k]), float(v[k]))


def vertex_ao(obj, ctx, dist=0.04, rays=24):
    """Per-vertex ambient occlusion (hemisphere rays against the hair itself and the body/clothing) -> attr 'ao'."""
    from mathutils.bvhtree import BVHTree
    own = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    other = ctx.outer_tree()
    co = gear.get_co(obj); vn = gear.vnormals(obj)
    rng = np.random.default_rng(1)
    dirs = rng.normal(0, 1, (rays, 3)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    ao = np.zeros(len(co))
    for i, (p, n) in enumerate(zip(co, vn)):
        hit = 0
        o = Vector(p + n * 0.0008)
        for d in dirs:
            d = d if d @ n > 0 else -d
            dv = Vector(d)
            if own.ray_cast(o, dv, dist)[0] is not None or other.ray_cast(o, dv, dist)[0] is not None:
                hit += 1
        ao[i] = 1 - hit / rays
    # one smoothing pass over the mesh neighbourhood removes ray noise
    me = obj.data
    acc = ao.copy(); cnt = np.ones(len(ao))
    ev = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", ev); ev = ev.reshape(-1, 2)
    np.add.at(acc, ev[:, 0], ao[ev[:, 1]]); np.add.at(acc, ev[:, 1], ao[ev[:, 0]])
    np.add.at(cnt, ev[:, 0], 1); np.add.at(cnt, ev[:, 1], 1)
    gear.set_attr(obj, "ao", acc / cnt)


def sculpt_hair(ctx, name, mat, out_tex, style, seed=3, voxel=None, target_tris=None):
    """Sculpted lock hair: lock tubes + scalp shell -> voxel union -> relax -> decimate. Painted in 3D: strands
    along the nearest lock direction, baked AO in the crevices, darker roots, lighter tips. Opaque (alpha 1)."""
    from mathutils.kdtree import KDTree
    curly = style == "curly"
    hc, eye, top = head_frame(ctx)
    locks, mask = lock_paths(ctx, style, seed)
    part = Part(name + "_tubes")
    for P, rad, T in locks:
        tube(part, P, rad, 7, mat=mat, caps=True)
    tubes = part.build(max_edge=None)
    # scalp shell (solid) so roots never show the scalp
    shell_o = gear.shell(ctx, name + "_scalp", mask, lambda P, N: np.full(len(P), 0.003 if curly else 0.004), mats=(mat,), smooth=6, subdiv=0,
                         rim=0.0, stack=False, cover=False, bsmooth=14, min_clear=0.0015)
    m = shell_o.modifiers.new("solid", "SOLIDIFY"); m.thickness = 0.008; m.offset = 1.0
    gear.apply_modifiers(shell_o)
    obj = gear.join([tubes, shell_o], name)
    m = obj.modifiers.new("remesh", "REMESH"); m.mode = "VOXEL"; m.voxel_size = voxel or (0.0025 if curly else 0.003); m.adaptivity = 0.0
    gear.apply_modifiers(obj)
    bm = bmesh.new(); bm.from_mesh(obj.data)
    for _ in range(2):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(obj.data); bm.free()
    # remove anything inside the head/body (hidden faces), then decimate to the budget
    co = gear.get_co(obj)
    inside = np.zeros(len(co), bool)
    for i, p in enumerate(co):
        hit, hn, _, _ = ctx.tree.find_nearest(Vector(p), 0.05)
        if hit is not None and (Vector(p) - hit).dot(hn) < -0.001:
            inside[i] = True
    bm = bmesh.new(); bm.from_mesh(obj.data); bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if inside[v.index]], context="VERTS")
    bm.to_mesh(obj.data); bm.free()
    tt = target_tris or (10800 if curly else 14000)
    cur = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if cur > tt:
        m = obj.modifiers.new("dec", "DECIMATE"); m.ratio = tt / cur
        gear.apply_modifiers(obj)
    obj.data.materials.clear(); obj.data.materials.append(gear.get_mat(mat))
    for p in obj.data.polygons:
        p.use_smooth = True
    if curly:
        set_sph_uv(obj, hc, (0.0, 0.0, 1.0, 1.0), (-75.0, 90.0))
    else:
        set_cyl_uv(obj, hc + np.array((0, 0.02, 0)))
    vertex_ao(obj, ctx, 0.035 if curly else 0.05)
    # ---- paint
    size = 2048
    T = TB.raster([obj], mat, size, attrs=("ao",), prefer="ao")
    idx = np.where(T.cov)[0]
    Pt = T.P[idx].astype(np.float64); Nt = T.N[idx].astype(np.float64)
    pts = np.concatenate([P for P, _, _ in locks]); tans = np.concatenate([Tg for _, _, Tg in locks])
    sN = np.concatenate([np.linspace(0, 1, len(P)) for P, _, _ in locks])
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(Vector(p), i)
    kd.balance()
    nearest = np.array([kd.find(Vector(p))[1] for p in Pt])
    tg = tans[nearest]
    tg = tg - Nt * (tg * Nt).sum(1, keepdims=True)
    tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    bi = np.cross(Nt, tg)
    # strands: fine lines parallel to the lock direction (coordinate across = P . bi), warped by noise
    across = (Pt * bi).sum(1) + 0.0015 * TB.fbm3(Pt, 90.0, 2, 1.0)
    st = np.clip(0.5 + 0.5 * np.sin(across / 0.0011 * math.pi) * (0.7 + 0.3 * TB.vnoise3(Pt, 400.0, 2.0)), 0, 1) ** 1.6
    st2 = 0.5 + 0.5 * np.sin(across / 0.00045 * math.pi + 3 * TB.vnoise3(Pt, 200.0, 4.0))
    clump = 0.5 + 0.5 * np.sin(across / 0.005 * math.pi + 2 * TB.fbm3(Pt, 40.0, 2, 3.0))
    tipk = sN[nearest]
    ao = np.clip(T.A["ao"][idx], 0, 1)
    dh = Pt - hc
    rr = np.linalg.norm(dh, axis=1)
    elv = np.degrees(np.arcsin(np.clip(dh[:, 2] / np.maximum(rr, 1e-9), -1, 1)))
    lum = (0.16 + 0.42 * st + 0.14 * st2 + 0.22 * clump) * (0.35 + 0.65 * ao ** 1.4) * (0.85 + 0.3 * tipk)
    if not curly:  # baked soft sheen band across the crown
        lum *= 1 + 0.35 * np.exp(-((elv - 48) / 9.0) ** 2) * (0.5 + 0.5 * st)
    root = ss(0.035, 0.0, rr - 0.105)
    lum *= 1 - 0.3 * root
    # wispy hairline: near the scalp edge the opaque mass breaks into strands (alpha-tested in Unity)
    azv = np.abs(np.arctan2(dh[:, 0], -dh[:, 1]))
    kn = [18, 17, 13, 8, 2, -14, -30, -36] if curly else [27, 25, 15, 6, -2, -18, -34, -40]
    el_min = np.interp(azv, np.radians([0, 30, 55, 80, 100, 125, 150, 180]), kn)
    edge = (elv - el_min) / 5.0
    near = (rr < 0.118) & (azv < np.radians(65)) & (not curly)
    edge = (elv - el_min) / 3.0
    alpha_t = np.where(near & (edge < 1.0), (st > 0.3 + 0.5 * (1 - np.clip(edge, 0, 1))).astype(np.float32), 1.0)
    img = np.zeros((size * size, 4), np.float32)
    base = np.array((0.20, 0.13, 0.09) if curly else (0.17, 0.11, 0.08)) * 2.4
    img[idx, :3] = lum[:, None] * base
    img[idx, 3] = alpha_t
    img = img.reshape(size, size, 4)
    a_keep = img[..., 3].copy()
    img = TB.dilate(img, T.cov.reshape(size, size), 8)
    img[..., 3] = np.where(T.cov.reshape(size, size), a_keep, 1.0)
    fn = f"Hair_{style}_Color.png"
    TB.write_png(np.clip(img, 0, 1), out_tex + "/" + fn, "RGBA")
    if not curly:
        tip = np.zeros(size * size, np.float32); tip[idx] = ss(0.6, 0.95, tipk)
        TB.write_png(np.stack([TB.dilate(tip.reshape(size, size), T.cov.reshape(size, size), 8)] * 3, -1), out_tex + "/Hair_wavy_Dye.png", "RGB")
    return obj, fn


def build_curly(ctx, name, out_tex, seed=3):
    return sculpt_hair(ctx, name, "Hair_curly", out_tex, "curly", seed)


def build_wavy(ctx, name, out_tex, seed=5):
    return sculpt_hair(ctx, name, "Hair_wavy", out_tex, "wavy", seed)
