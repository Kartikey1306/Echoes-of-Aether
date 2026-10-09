"""Kael concept face sculpt (rugged, handsome): a heavier brow ridge that sits low over deeper-set eyes, sculpted
cheekbones with a hollow under them, a wider squarer jaw and chin, a straight strong nose bridge and a touch of
asymmetry. A smooth displacement field on the rest head (a few millimetres), added to the basis and to every shape
key of the body (their deltas stay unchanged) and carried to the attached meshes (brows, lashes, facial hair) by
their nearest skin vertex. The head stays within ~4 mm of the previous one (catalog hair / eyewear still fit).
"""
import numpy as np
from mathutils.kdtree import KDTree
import kcommon as K
from kcommon import ss, nrm
import meshops


def landmarks(co, L):
    eye = (L["LeftEye"] + L["RightEye"]) / 2
    mid = co[(np.abs(co[:, 0]) < 0.004) & (co[:, 2] < eye[2] + 0.1) & (co[:, 2] > eye[2] - 0.16) & (co[:, 1] < eye[1] + 0.02)]
    nose = mid[np.argmin(mid[:, 1] + np.where(mid[:, 2] > eye[2] - 0.02, 1, 0))]
    mouth = np.array((0.0, nose[1] + 0.012, nose[2] - 0.034))
    low = mid[mid[:, 2] < nose[2] - 0.012]
    chin = low[np.argmin(low[:, 1] + np.abs(low[:, 2] - (nose[2] - 0.065)) * 2)]
    return eye, nose, mouth, chin


def field(co, L, head_w):
    """Displacement (n, 3) in metres."""
    eye, nose, mouth, chin = landmarks(co, L)
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    ax = np.abs(x)
    sx = np.sign(x)
    d = np.zeros_like(co)
    front = ss(eye[1] + 0.06, eye[1] + 0.03, y) * (head_w > 0.5)
    g = lambda c, s: np.exp(-np.sum(((co - c) / np.asarray(s)) ** 2, 1))
    # 1. brow ridge: forward and a little down along the brow arch (highest mid-brow, lower at the outer end)
    zb = eye[2] + 0.017 + 0.005 * ss(0.0, 0.03, ax) - 0.008 * ss(0.036, 0.062, ax)
    wb = np.exp(-((z - zb) / 0.0072) ** 2) * ss(0.066, 0.05, ax) * front * (y < eye[1] + 0.012)
    d[:, 1] -= 0.0032 * wb
    d[:, 2] -= 0.001 * wb
    # 2. cheekbones out, hollow under them
    for s in (1, -1):
        out = nrm(np.array((s * 0.75, -0.66, 0.05)))
        d += out[None] * (0.003 * g(np.array((s * 0.05, eye[1] + 0.012, eye[2] - 0.027)), (0.014, 0.012, 0.011)) * front)[:, None]
        inn = nrm(np.array((s * 0.6, -0.8, 0.0)))
        d -= inn[None] * (0.0026 * g(np.array((s * 0.046, eye[1] + 0.024, eye[2] - 0.052)), (0.012, 0.012, 0.012)) * front)[:, None]
    # 3. wider, squarer jaw: the jaw angle and the lower jaw line out
    jaw = ss(0.028, 0.052, ax) * np.exp(-((z - (mouth[2] - 0.03)) / 0.022) ** 2) * ss(eye[1] + 0.11, eye[1] + 0.075, y) * (head_w > 0.3)
    d[:, 0] += sx * 0.0022 * jaw
    d[:, 2] -= 0.001 * jaw
    # defined jaw angle: the corner pushed out and down a touch more
    for s in (1, -1):
        ja = g(np.array((s * 0.058, eye[1] + 0.07, mouth[2] - 0.045)), (0.012, 0.014, 0.012)) * (head_w > 0.3)
        d[:, 0] += s * 0.0014 * ja
        d[:, 2] -= 0.0012 * ja
    # 4. square chin: wider, a little forward
    wc = g(chin + np.array((0, 0.004, 0.004)), (0.024, 0.016, 0.014)) * front
    d[:, 0] += sx * 0.0016 * wc * ss(0.0, 0.012, ax)
    d[:, 1] -= 0.001 * wc
    # 5. straight, strong nose bridge
    wn = np.exp(-(x / 0.007) ** 2) * ss(eye[2] + 0.012, eye[2] - 0.004, z) * ss(nose[2] + 0.004, nose[2] + 0.02, z) * front
    d[:, 1] -= 0.0009 * wn
    # 6. closed mouth: the lips meet (the base mesh shows a gap with the teeth behind it)
    lip = np.exp(-(x / 0.022) ** 4) * front * (y < mouth[1] + 0.012)
    up_l = np.exp(-((z - (mouth[2] + 0.004)) / 0.0035) ** 2) * (z > mouth[2] - 0.0005)
    lo_l = np.exp(-((z - (mouth[2] - 0.004)) / 0.0035) ** 2) * (z < mouth[2] + 0.0005)
    d[:, 2] += (-0.0007 * up_l + 0.0006 * lo_l) * lip
    # 7. eyelids: a defined upper-lid crease, a rounded (thicker) lower-lid margin and the tear trough under it
    for S, s in (("LeftEye", 1), ("RightEye", -1)):
        e = L[S]
        q = co - e
        r = np.hypot(q[:, 0] / 1.15, q[:, 2])
        fr = (q[:, 1] < -0.004) * front
        up_ = ss(-0.002, 0.004, q[:, 2])
        lo_ = ss(0.002, -0.004, q[:, 2])
        d[:, 1] += 0.00055 * np.exp(-((r - 0.0158) / 0.0016) ** 2) * up_ * fr          # crease (pushed in)
        d[:, 1] -= 0.0003 * np.exp(-((r - 0.0128) / 0.0011) ** 2) * lo_ * fr           # lower-lid margin rolls out
        d[:, 1] += 0.00035 * np.exp(-((r - 0.0205) / 0.0022) ** 2) * lo_ * fr * ss(-0.02, -0.005, q[:, 0] * s)   # tear trough (inner)
    # 8. nasolabial folds: groove from the nose wing to outside the mouth corner, cheek fullness above it
    for s in (1, -1):
        a_ = np.array((s * 0.0175, nose[1] + 0.012, nose[2] - 0.002)); b_ = np.array((s * 0.031, mouth[1] + 0.01, mouth[2] - 0.014))
        dd_ = b_ - a_
        t = np.clip(((co - a_) @ dd_) / (dd_ @ dd_), 0, 1)
        dist = np.linalg.norm(co - (a_ + t[:, None] * dd_), axis=1)
        env = ss(0.0, 0.2, t) * ss(1.0, 0.75, t) * front
        side = (co[:, 0] - (a_[0] + t * dd_[0])) * s
        d[:, 1] += 0.0007 * np.exp(-(dist / 0.0026) ** 2) * env
        d[:, 1] -= 0.0005 * np.exp(-((dist - 0.006) / 0.004) ** 2) * env * (side > 0)
    # 9. philtrum ridges and groove, chin cleft, masseter (jaw muscle)
    phz = ss(mouth[2] + 0.004, mouth[2] + 0.008, z) * ss(nose[2] - 0.006, nose[2] - 0.012, z) * front
    d[:, 1] -= 0.00028 * np.exp(-((ax - 0.0052) / 0.0018) ** 2) * phz
    d[:, 1] += 0.0002 * np.exp(-(x / 0.002) ** 2) * phz
    cc = chin + np.array((0, 0.0, 0.004))
    d[:, 1] += 0.0008 * np.exp(-(x / 0.0026) ** 2 - ((z - cc[2]) / 0.008) ** 2) * front * (y < cc[1] + 0.01)
    for s in (1, -1):
        mm = g(np.array((s * 0.056, eye[1] + 0.06, mouth[2] - 0.012)), (0.012, 0.016, 0.018)) * (head_w > 0.3)
        d[:, 0] += s * 0.0011 * mm
    # 10. slight asymmetry: his left brow a touch higher (scar side), right mouth corner a hair up
    d[:, 2] += 0.0006 * wb * (x > 0)
    d[:, 2] += 0.0004 * g(mouth + np.array((-0.024, 0.006, 0.0)), (0.008, 0.01, 0.008)) * front
    return d


def smooth_field(o, d, iters=6):
    E = meshops.edges_of(o)
    n = len(d)
    for _ in range(iters):
        d = d * 0.5 + meshops.neighbor_mean(d, E, n) * 0.5
    return d


def shift_all(o, delta):
    """Add delta to the basis and every shape key of o (key deltas unchanged)."""
    me = o.data
    nv = len(me.vertices)
    if me.shape_keys:
        for k in me.shape_keys.key_blocks:
            c = np.zeros(nv * 3); k.data.foreach_get("co", c)
            k.data.foreach_set("co", (c.reshape(-1, 3) + delta).ravel())
        c = np.zeros(nv * 3); me.shape_keys.key_blocks[0].data.foreach_get("co", c)
        me.vertices.foreach_set("co", c)
    else:
        K.set_co(o, K.get_co(o) + delta)
    me.update()


def apply(body, rig, others=(), store=True):
    L = {b.name.split(":")[1]: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones if ":" in b.name}
    co = K.get_co(body)
    g = body.vertex_groups.get("mixamorig:Head")
    hw = np.zeros(len(co))
    if g:
        for v in body.data.vertices:
            for gg in v.groups:
                if gg.group == g.index:
                    hw[v.index] = gg.weight
    d = smooth_field(body, field(co, L, hw))
    shift_all(body, d)
    if store:
        for k, ax_ in (("k_sx", 0), ("k_sy", 1), ("k_sz", 2)):
            a = body.data.attributes.get(k) or body.data.attributes.new(k, "FLOAT", "POINT")
            a.data.foreach_set("value", d[:, ax_].astype(np.float32))
    kd = KDTree(len(co))
    for i, c in enumerate(co):
        kd.insert(c, i)
    kd.balance()
    for o in others:
        if o is None:
            continue
        transfer(o, kd, co, d)
        if o.name == "Brows":
            fuller_brows(o)
    K.log("SCULPT face max mm", round(float(np.linalg.norm(d, axis=1).max()) * 1000, 2))
    return d


def transfer(o, kd, co, d, reach=0.012):
    pts = np.array([o.matrix_world @ v.co for v in o.data.vertices])
    dd = np.zeros_like(pts)
    for i, p in enumerate(pts):
        c, j, dist = kd.find(p)
        dd[i] = d[j] * ss(reach, reach * 0.4, dist)
    shift_all(o, dd)


def fuller_brows(o, scale=1.6, drop=0.0026, straight=0.55):
    """Concept brows: thicker (scaled about each brow's centre line) and sitting a little lower over the eyes."""
    co = np.array([v.co[:] for v in o.data.vertices])
    out = np.zeros_like(co)
    bins = np.linspace(-0.07, 0.07, 29)
    zc = np.zeros(len(co))
    for s_ in (1, -1):
        m = np.sign(co[:, 0]) == s_
        xs, zs = [], []
        for b0, b1 in zip(bins[:-1], bins[1:]):
            q = m & (co[:, 0] >= b0) & (co[:, 0] < b1)
            if q.sum() >= 2:
                xs.append((b0 + b1) / 2); zs.append(co[q, 2].mean())
        if len(xs) >= 2:
            zc[m] = np.interp(co[m, 0], xs, zs)
    # final pass: straighter (pull the arched centre line towards a straight line per brow) and lower
    zl = np.zeros(len(co))
    for s_ in (1, -1):
        m = np.sign(co[:, 0]) == s_
        if m.sum() > 3:
            A = np.c_[co[m, 0], np.ones(int(m.sum()))]
            k_, b_ = np.linalg.lstsq(A, zc[m], rcond=None)[0]
            zl[m] = k_ * co[m, 0] + b_
    out[:, 2] = (co[:, 2] - zc) * (scale - 1.0) + (zl - zc) * straight - drop
    shift_all(o, out)
