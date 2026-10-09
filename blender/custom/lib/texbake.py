# SNAPSHOT of blender/scripts/texbake.py taken 2026-10-04 for the customisation pipeline (blender/custom). Do not edit; re-copy if needed.
"""Texture atlas toolkit for the HD character pipeline.

pack():     packs the UV islands of every face that uses a material (across several meshes) into one 0..1 atlas
raster():   rasterises those faces into texel arrays: rest position, normal, body-space position, custom vertex
            attributes and metres-per-texel (for physically scaled detail)
bake_ao():  Cycles ambient-occlusion bake of an atlas (all visible scene geometry occludes)
Helpers for height -> normal conversion, dilation, noise and PNG output.
"""
import os, math
import numpy as np
import bpy


# ----------------------------------------------------------------------------- UV packing


def _faces_with(obj, mat):
    names = [m.name if m else "" for m in obj.data.materials]
    if mat not in names:
        return None
    idx = names.index(mat)
    return idx


def _islands(me, faces, uv):
    """Connected UV islands (lists of polygon indices) among `faces`: faces sharing a vertex with equal UVs."""
    parent = {f: f for f in faces}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    key = {}
    for f in faces:
        p = me.polygons[f]
        for li in p.loop_indices:
            v = me.loops[li].vertex_index
            k = (v, round(uv[li][0], 5), round(uv[li][1], 5))
            if k in key:
                ra, rb = find(key[k]), find(f)
                if ra != rb:
                    parent[ra] = rb
            else:
                key[k] = f
    groups = {}
    for f in faces:
        groups.setdefault(find(f), []).append(f)
    return list(groups.values())


def pack(objs, mat, margin=0.004, rotate=True, weights=None, island_weight=None):
    """Shelf-pack the UV islands of all faces using `mat` (several meshes) into one 0..1 atlas with uniform texel
    density (island UVs rescaled to their 3D area). weights: {obj_name: density multiplier}."""
    objs = [o for o in objs if _faces_with(o, mat) is not None]
    isl = []  # (obj, faces, uvcoords array per loop dict, area3d)
    for o in objs:
        me = o.data
        idx = _faces_with(o, mat)
        uvl = me.uv_layers.active.data
        uv = np.empty(len(me.loops) * 2); uvl.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        faces = [p.index for p in me.polygons if p.material_index == idx]
        for grp in _islands(me, faces, uv):
            loops = [li for f in grp for li in me.polygons[f].loop_indices]
            a3 = a2 = 0.0
            for f in grp:
                p = me.polygons[f]
                lis = list(p.loop_indices)
                vs = [me.loops[li].vertex_index for li in lis]
                for k in range(1, len(lis) - 1):
                    a3 += np.linalg.norm(np.cross(co[vs[k]] - co[vs[0]], co[vs[k + 1]] - co[vs[0]])) * 0.5
                    u0, u1, u2 = uv[lis[0]], uv[lis[k]], uv[lis[k + 1]]
                    a2 += abs((u1[0] - u0[0]) * (u2[1] - u0[1]) - (u2[0] - u0[0]) * (u1[1] - u0[1])) * 0.5
            L = np.array(loops)
            w = (weights or {}).get(o.name, 1.0) * (island_weight(grp, uv[L]) if island_weight else 1.0)
            sc = math.sqrt(a3 / max(a2, 1e-12)) * w if a2 > 1e-12 else 0.0
            U = uv[L] * sc
            if sc == 0.0:
                U = np.zeros((len(L), 2)) + 0.0005
            mn = U.min(0); U -= mn
            ext = U.max(0)
            isl.append([o, L, U, ext, a3])
    if not isl:
        return objs
    # rotate tall islands so shelves stay tidy
    for it in isl:
        if rotate and it[3][1] > it[3][0] * 1.15:
            it[2] = np.stack([it[2][:, 1], it[3][0] - it[2][:, 0]], 1)
            it[3] = it[3][::-1].copy()
    total = sum(max(e[0], 1e-5) * max(e[1], 1e-5) for _, _, _, e, _ in isl)
    order = sorted(range(len(isl)), key=lambda i: -isl[i][3][1])
    scale = 0.92 / math.sqrt(total)
    for _ in range(60):
        placed, x, y, shelf_h, ok = {}, 0.0, 0.0, 0.0, True
        for i in order:
            w, h = isl[i][3] * scale + margin
            if x + w > 1.0:
                x, y = 0.0, y + shelf_h
                shelf_h = 0.0
            if y + h > 1.0 or w > 1.0:
                ok = False
                break
            placed[i] = (x + margin * 0.5, y + margin * 0.5)
            x += w
            shelf_h = max(shelf_h, h)
        if ok:
            break
        scale *= 0.96
    for i, (o, L, U, ext, a3) in enumerate(isl):
        ox, oy = placed[i]
        uvl = o.data.uv_layers.active.data
        for k, li in enumerate(L):
            uvl[li].uv = (ox + U[k, 0] * scale, oy + U[k, 1] * scale)
    return objs


def pack_weighted(obj, mat, fn, margin=0.004):
    return pack([obj], mat, margin=margin, island_weight=fn)


# ----------------------------------------------------------------------------- rasteriser


class Texels:
    """Per-texel data for one atlas."""

    def __init__(self, size, attrs):
        self.size = size
        n = size * size
        self.cov = np.zeros(n, bool)
        self.P = np.zeros((n, 3), np.float32)
        self.N = np.zeros((n, 3), np.float32)
        self.mpt = np.zeros(n, np.float32)
        self.obj = np.full(n, -1, np.int16)
        self.A = {k: np.zeros(n, np.float32) for k in attrs}

    def img(self, a):
        return np.asarray(a).reshape(self.size, self.size, *np.asarray(a).shape[1:])


def raster(objs, mat, size, attrs=("bx", "by", "bz", "wear", "cavity", "lx", "ly", "plate", "pouch", "strap", "sole", "collar", "back"), uv2=None):
    T = Texels(size, attrs)
    T.UV2 = np.zeros((size * size, 2), np.float32) if uv2 else None
    objs = [o for o in objs if _faces_with(o, mat) is not None]
    T.names = [o.name for o in objs]
    for oi, o in enumerate(objs):
        me = o.data
        idx = _faces_with(o, mat)
        me.calc_loop_triangles()
        uvd = np.empty(len(me.loops) * 2)
        uvact = me.uv_layers.active if me.uv_layers.active.name != "UVOld" else me.uv_layers[0]
        uvact.data.foreach_get("uv", uvd)
        uvd = uvd.reshape(-1, 2)
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        vn = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("normal", vn); vn = vn.reshape(-1, 3)
        av = {}
        for k in attrs:
            at = me.attributes.get(k)
            if at is not None and at.domain == "POINT" and len(at.data) == len(me.vertices):
                a = np.empty(len(at.data)); at.data.foreach_get("value", a); av[k] = a
        has_b = all(k in av for k in ("bx", "by", "bz"))
        if uv2:
            u2 = np.empty(len(me.loops) * 2); me.uv_layers[uv2].data.foreach_get("uv", u2); u2 = u2.reshape(-1, 2)
        ntri = len(me.loop_triangles)
        tl = np.empty(ntri * 3, np.int64); me.loop_triangles.foreach_get("loops", tl); tl = tl.reshape(-1, 3)
        tv = np.empty(ntri * 3, np.int64); me.loop_triangles.foreach_get("vertices", tv); tv = tv.reshape(-1, 3)
        tm = np.empty(ntri, np.int64); me.loop_triangles.foreach_get("material_index", tm)
        for t in np.where(tm == idx)[0]:
            uvs = uvd[tl[t]] * size
            vi = tv[t]
            x0, y0 = np.floor(uvs.min(0)).astype(int)
            x1, y1 = np.ceil(uvs.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, size - 1), min(y1, size - 1)
            if x1 < x0 or y1 < y0:
                continue
            a, b, c = uvs
            v0, v1 = b - a, c - a
            den = v0[0] * v1[1] - v1[0] * v0[1]
            if abs(den) < 1e-10:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            px = xs.ravel() - a[0]; py = ys.ravel() - a[1]
            w1 = (px * v1[1] - v1[0] * py) / den
            w2 = (v0[0] * py - px * v0[1]) / den
            w0 = 1 - w1 - w2
            inside = (w0 >= -1e-3) & (w1 >= -1e-3) & (w2 >= -1e-3)
            if not inside.any():
                continue
            W = np.stack([w0, w1, w2], 1)[inside]
            pix = (ys.ravel()[inside].astype(int)) * size + xs.ravel()[inside].astype(int)
            P = W @ co[vi]
            N = W @ vn[vi]
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            T.P[pix] = P
            T.N[pix] = N
            T.cov[pix] = True
            T.obj[pix] = oi
            area3 = np.linalg.norm(np.cross(co[vi[1]] - co[vi[0]], co[vi[2]] - co[vi[0]])) * 0.5
            area2 = abs(den) * 0.5
            T.mpt[pix] = math.sqrt(area3 / max(area2, 1e-9))
            for k, a_ in av.items():
                T.A[k][pix] = W @ a_[vi]
            if uv2:
                T.UV2[pix] = W @ u2[tl[t]]
            if not has_b:
                for k, comp in zip(("bx", "by", "bz"), range(3)):
                    if k in T.A:
                        T.A[k][pix] = P[:, comp]
    # fill metres-per-texel holes with the median so detail scales stay sane
    med = np.median(T.mpt[T.cov]) if T.cov.any() else 0.001
    T.mpt[~T.cov] = med
    T.mpt = np.clip(T.mpt, med * 0.25, med * 4)
    return T


def dilate(img, cov, iters=8):
    img = img.copy(); cov = cov.copy()
    for _ in range(iters):
        acc = np.zeros_like(img); cnt = np.zeros(cov.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sc = np.roll(np.roll(cov, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * (sc[..., None] if img.ndim == 3 else sc)
            cnt += sc
        grow = (~cov) & (cnt > 0)
        if img.ndim == 3:
            img[grow] = acc[grow] / cnt[grow][:, None]
        else:
            img[grow] = acc[grow] / cnt[grow]
        cov |= grow
    return img


def blur(img, r=1):
    out = img.astype(np.float32).copy()
    for _ in range(r):
        out = (out + np.roll(out, 1, 0) + np.roll(out, -1, 0) + np.roll(out, 1, 1) + np.roll(out, -1, 1)) / 5.0
    return out


def height_to_normal(h, mpt, strength=1.0):
    """h: height in metres (HxW); mpt: metres per texel (HxW). Returns OpenGL-convention normal map 0..1 (HxWx3)."""
    gy, gx = np.gradient(h)
    gx = gx / mpt * strength
    gy = gy / mpt * strength
    n = np.stack([-gx, -gy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def write_png(arr, path, mode=None):
    """arr: (H,W[,C]) float 0..1 with row 0 = v 0 (bottom). Writes an 8-bit PNG (L, RGB or RGBA)."""
    import zlib, struct
    arr = np.clip(np.asarray(arr, np.float32), 0, 1)
    if arr.ndim == 2:
        arr = arr[..., None]
    c = arr.shape[2]
    if mode == "RGB" and c == 4:
        arr = arr[..., :3]; c = 3
    if mode == "RGBA" and c == 3:
        arr = np.concatenate([arr, np.ones(arr.shape[:2] + (1,), np.float32)], -1); c = 4
    color_type = {1: 0, 3: 2, 4: 6}[c]
    data = (arr[::-1] * 255 + 0.5).astype(np.uint8)
    h, w = data.shape[:2]
    rows = data.reshape(h, w * c).astype(np.int16)
    filt = rows.copy()
    filt[:, c:] = (rows[:, c:] - rows[:, :-c]) % 256  # PNG "Sub" filter
    raw = np.concatenate([np.ones((h, 1), np.uint8), filt.astype(np.uint8)], 1).tobytes()

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 7)))
        f.write(chunk(b"IEND", b""))


def read_image(path, size=None):
    """Load an image file into a float array (H,W,4), row 0 = bottom (Blender convention). Optional resample."""
    im = bpy.data.images.load(path, check_existing=False)
    im.colorspace_settings.name = "Non-Color"
    if size and (im.size[0] != size or im.size[1] != size):
        im.scale(size, size)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)


def sample(img, uv):
    """Bilinear sample of img (H,W,C) at uv (N,2) in 0..1 (v up)."""
    h, w = img.shape[:2]
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1.001)
    y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


# ----------------------------------------------------------------------------- AO bake


def bake_ao(targets, mat, size, samples=16, distance=0.12, hide=(), scale=0.5):
    """Bake AO for the faces using `mat` on `targets` into a size^2 array (1 = open, 0 = occluded).
    Baked at size*scale and upsampled (AO is low frequency)."""
    full_size = size
    size = max(256, int(size * scale))
    sc = bpy.context.scene
    prev_engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    if sc.world is None:
        sc.world = bpy.data.worlds.new("bake_world")
    sc.world.light_settings.distance = distance
    hidden = []
    for o in hide:
        if not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    img = bpy.data.images.new("bake_" + mat, size, size, alpha=False, float_buffer=True)
    dummy = bpy.data.images.new("bake_dummy", 16, 16, alpha=False)
    added = []
    targets = [t for t in targets if _faces_with(t, mat) is not None]
    for o in targets:
        for m in o.data.materials:
            if m is None:
                continue
            m.use_nodes = True
            nt = m.node_tree
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = img if m.name == mat else dummy
            n.interpolation = "Closest"
            nt.nodes.active = n
            added.append((nt, n))
    bpy.ops.object.select_all(action="DESELECT")
    for o in targets:
        o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.ops.object.bake(type="AO", margin=6, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    a = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(a)
    ao = a.reshape(size, size, 4)[..., 0].copy()
    for nt, n in added:
        nt.nodes.remove(n)
    bpy.data.images.remove(img)
    bpy.data.images.remove(dummy)
    for o in hidden:
        o.hide_render = False
    for o in targets:
        o.select_set(False)
    sc.render.engine = prev_engine
    if size != full_size:
        k = full_size // size
        ao = np.kron(ao, np.ones((k, k), np.float32))
        ao = blur(ao, 1)
    return ao


# ----------------------------------------------------------------------------- procedural detail (numpy)


def hash2(ix, iy, seed=0.0):
    h = np.sin(ix * 127.1 + iy * 311.7 + seed * 74.7) * 43758.5453
    return h - np.floor(h)


def hash3(P, seed=0.0):
    h = np.sin(P[..., 0] * 127.1 + P[..., 1] * 311.7 + P[..., 2] * 74.7 + seed * 19.19) * 43758.5453
    return h - np.floor(h)


def vnoise3(P, freq, seed=0.0):
    Q = np.asarray(P, np.float64) * freq + seed * 13.7
    i = np.floor(Q)
    f = Q - i
    f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                g = i + np.array((dx, dy, dz))
                w = (f[..., 0] if dx else 1 - f[..., 0]) * (f[..., 1] if dy else 1 - f[..., 1]) * (f[..., 2] if dz else 1 - f[..., 2])
                out = out + w * hash3(g, seed)
    return out * 2 - 1


def fbm3(P, freq, octaves=4, seed=0.0, gain=0.5):
    out, amp, tot = 0.0, 1.0, 0.0
    for k in range(octaves):
        out = out + amp * vnoise3(P, freq * (2.03 ** k), seed + k * 7.3)
        tot += amp
        amp *= gain
    return out / tot


def worley3(P, freq, seed=0.0, chunk=400000):
    """F1 cellular distance (in cell units) of 3D points, chunked."""
    P = np.asarray(P, np.float64)
    out = np.empty(len(P), np.float32)
    for s in range(0, len(P), chunk):
        Q = P[s:s + chunk] * freq
        i = np.floor(Q)
        best = np.full(len(Q), 9.0)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    g = i + np.array((dx, dy, dz))
                    fp = g + np.stack([hash3(g, seed), hash3(g, seed + 1.3), hash3(g, seed + 2.7)], -1)
                    d = np.linalg.norm(Q - fp, axis=1)
                    best = np.minimum(best, d)
        out[s:s + chunk] = best
    return out


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def line_sdf2(px, py, ax, ay, bx, by):
    """Distance from 2D points to the segment a-b (arrays)."""
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-12), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy)), t
