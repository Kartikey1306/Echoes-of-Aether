"""UV-space rasterisation of mesh data (positions, smooth normals, MikkTSpace tangent frames, attributes) and
texture-space utilities (dilation, blur, normals from height)."""
import bpy, math
import numpy as np
import gv


class Maps:
    """Per-texel data for one atlas (row 0 = bottom = v 0, like Blender images)."""

    def __init__(self, size):
        self.size = size
        s = (size, size)
        self.mask = np.zeros(s, bool)
        self.P = np.zeros(s + (3,), np.float32)
        self.N = np.zeros(s + (3,), np.float32)
        self.T = np.zeros(s + (3,), np.float32)
        self.B = np.zeros(s + (3,), np.float32)
        self.J = np.zeros(s + (3, 2), np.float32)     # dP/du, dP/dv (metres per uv unit)
        self.obj = np.full(s, -1, np.int16)
        self.attr = {}

    def add_attr(self, name):
        if name not in self.attr:
            self.attr[name] = np.zeros((self.size, self.size), np.float32)
        return self.attr[name]


def loop_data(o, uv_name=None):
    """Triangles of o with per-corner uv, position, normal, tangent, bitangent and face index."""
    me = o.data
    X = gv.basis_co(o)
    tris = gv.tri_index(me)
    vn = gv.vertex_normals(X, tris)
    uvl = me.uv_layers[uv_name] if uv_name else me.uv_layers.active
    me.calc_tangents(uvmap=uvl.name)
    nl = len(me.loops)
    uv = np.empty(nl * 2, np.float32)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    tan = np.empty(nl * 3, np.float32)
    me.loops.foreach_get("tangent", tan)
    tan = tan.reshape(-1, 3)
    bsign = np.empty(nl, np.float32)
    me.loops.foreach_get("bitangent_sign", bsign)
    lnor = np.empty(nl * 3, np.float32)
    me.loops.foreach_get("normal", lnor)
    lnor = lnor.reshape(-1, 3)
    lt = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", lt)
    lt = lt.reshape(-1, 3)
    fi = np.empty(len(me.loop_triangles), np.int32)
    me.loop_triangles.foreach_get("polygon_index", fi)
    lv = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", lv)
    return dict(X=X, vn=vn, uv=uv, tan=tan, bsign=bsign, lnor=lnor, lt=lt, fi=fi, lv=lv)


def rasterize(maps, o, oid, face_mask=None, vattrs=(), fattrs=()):
    """Write o's triangles (optionally only faces in face_mask) into maps."""
    S = maps.size
    D = loop_data(o)
    me = o.data
    va = {}
    for n in vattrs:
        if n in me.attributes:
            a = np.zeros(len(me.vertices), np.float32)
            me.attributes[n].data.foreach_get("value", a)
            va[n] = a
            maps.add_attr(n)
    fa = {}
    for n in fattrs:
        if n in me.attributes:
            a = np.zeros(len(me.polygons), np.float32)
            me.attributes[n].data.foreach_get("value", a)
            fa[n] = a
            maps.add_attr(n)
    X, vn, uv, tan, bs, lt, fi, lv = D["X"], D["vn"], D["uv"], D["tan"], D["bsign"], D["lt"], D["fi"], D["lv"]
    for t in range(len(lt)):
        f = fi[t]
        if face_mask is not None and not face_mask[f]:
            continue
        L = lt[t]
        V = lv[L]
        q = uv[L] * S - 0.5                       # pixel centres at integer coords
        x0, y0 = np.floor(q.min(0)).astype(int)
        x1, y1 = np.ceil(q.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, S - 1), min(y1, S - 1)
        if x1 < x0 or y1 < y0:
            continue
        a, b, c = q
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        w0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        w2 = 1 - w0 - w1
        e = -0.6 / max(abs(den), 1.0) ** 0.5       # conservative: include edge texels
        inside = (w0 >= e) & (w1 >= e) & (w2 >= e)
        if not inside.any():
            continue
        yy, xx = ys[inside], xs[inside]
        W = np.stack([w0[inside], w1[inside], w2[inside]], 1)
        W = np.clip(W, 0, None)
        W /= W.sum(1, keepdims=True)
        P_ = W @ X[V]
        N_ = W @ vn[V]
        T_ = W @ tan[L]
        maps.P[yy, xx] = P_
        maps.N[yy, xx] = gv.nrm(N_)
        Tn = T_ - maps.N[yy, xx] * (T_ * maps.N[yy, xx]).sum(1, keepdims=True)
        Tn = gv.nrm(Tn)
        maps.T[yy, xx] = Tn
        maps.B[yy, xx] = np.cross(maps.N[yy, xx], Tn) * bs[L[0]]
        # Jacobian dP/d(uv) of this triangle
        Puv = np.array([uv[L[1]] - uv[L[0]], uv[L[2]] - uv[L[0]]]).T          # 2x2
        Pxyz = np.array([X[V[1]] - X[V[0]], X[V[2]] - X[V[0]]]).T             # 3x2
        try:
            J = Pxyz @ np.linalg.inv(Puv)
        except np.linalg.LinAlgError:
            J = np.zeros((3, 2))
        maps.J[yy, xx] = J
        maps.mask[yy, xx] = True
        maps.obj[yy, xx] = oid
        for n, a in va.items():
            maps.attr[n][yy, xx] = W @ a[V]
        for n, a in fa.items():
            maps.attr[n][yy, xx] = a[f]
    return maps


# ----------------------------------------------------------------------------- texture-space utilities

def dilate(img, mask, px=8):
    """Grow island colours outward by px texels (avoids seams with mip-mapping)."""
    img = img.copy()
    m = mask.copy()
    for _ in range(px):
        if m.all():
            break
        acc = np.zeros_like(img, dtype=np.float32)
        cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sm = np.roll(np.roll(m, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            add = sm & ~m
            if img.ndim == 3:
                acc[add] += si[add]
            else:
                acc[add] += si[add]
            cnt[add] += 1
        new = cnt > 0
        if img.ndim == 3:
            img[new] = acc[new] / cnt[new][:, None]
        else:
            img[new] = acc[new] / cnt[new]
        m |= new
    return img


def blur(img, r=1, mask=None):
    """Box blur (separable, r texels) restricted to mask texels if given."""
    out = img.astype(np.float32)
    for axis in (0, 1):
        acc = np.zeros_like(out)
        n = 0
        for k in range(-r, r + 1):
            acc += np.roll(out, k, axis)
            n += 1
        out = acc / n
    if mask is not None:
        out = np.where(mask[..., None] if out.ndim == 3 else mask, out, img)
    return out


def normals_from_height(maps, h, strength=1.0):
    """Tangent-space normal map (RGB 0..1, OpenGL / Unity convention) from a height field h (metres) defined
    per texel; the surface gradient is computed through each texel's uv Jacobian."""
    S = maps.size
    hu = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * S        # dh per uv unit (u = x = axis 1)
    hv = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * S
    # invalid neighbours (outside islands): one-sided / zero
    m = maps.mask
    okx = np.roll(m, -1, 1) & np.roll(m, 1, 1)
    oky = np.roll(m, -1, 0) & np.roll(m, 1, 0)
    hu[~okx] = 0
    hv[~oky] = 0
    J = maps.J
    G = np.einsum("...ij,...jk->...ik", np.swapaxes(J, -1, -2), J)          # 2x2 metric
    det = G[..., 0, 0] * G[..., 1, 1] - G[..., 0, 1] * G[..., 1, 0]
    det = np.where(np.abs(det) < 1e-20, 1e-20, det)
    inv = np.stack([np.stack([G[..., 1, 1], -G[..., 0, 1]], -1), np.stack([-G[..., 1, 0], G[..., 0, 0]], -1)], -2) / det[..., None, None]
    huv = np.stack([hu, hv], -1)
    g = np.einsum("...ij,...jk,...k->...i", J, inv, huv) * strength      # surface gradient (3D)
    n = gv.nrm(maps.N - g)
    tx = (n * maps.T).sum(-1)
    ty = (n * maps.B).sum(-1)
    tz = (n * maps.N).sum(-1)
    out = np.stack([tx, ty, tz], -1)
    out = gv.nrm(out)
    rgb = out * 0.5 + 0.5
    rgb[~m] = (0.5, 0.5, 1.0)
    return rgb
