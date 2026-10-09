"""Face and skin for the HD pipeline.

rebuild_eyes()    new eyeballs per eye: UV sphere with a corneal bulge (catches a crisp highlight), weights to the eye
                  bones, morph shapes via binding; UV layout puts the iris at the texture centre so Unity's
                  CharacterModel.ApplyEyes iris tint (ellipse d = sqrt(4dx^2+dy^2) < ~0.085) lands on the iris.
eye_textures()    procedural eye textures (sclera veins, limbal ring, fibrous iris, pupil) in that layout.
decimate_with_shapes()  decimates a mesh and rebuilds its blendshapes/weights through a surface binding.
relayout_body()   after hidden faces are stripped, re-packs the remaining Body UV islands (head favoured) so the
                  visible skin gets far more texels; keeps the MakeHuman UVs in a second layer for resampling.
skin_textures()   Skin_<tone>.png (MakeHuman CC0 skins resampled + pores, redness, beard/scalp shadow, tattoo ink),
                  Skin_Normal.png (pores, wrinkles), Skin_MaskMap.png (R metal 0, G cavity AO, B thickness, A smoothness),
                  Skin_Tattoo.png (RGB emission) + Skin_TattooMask.png.
"""
import os, math
import numpy as np
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import gear
from gear import nrm, ss
import texbake as TB
from meshutil import SurfaceBinding, add_shape_key

MPFB_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")


# ----------------------------------------------------------------------------- eyes


def _components(me):
    parent = list(range(len(me.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    comps = {}
    for v in range(len(me.vertices)):
        comps.setdefault(find(v), []).append(v)
    return list(comps.values())


def _fit_sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    b = (P ** 2).sum(1)
    x = np.linalg.lstsq(A, b, rcond=None)[0]
    c = x[:3]
    return c, math.sqrt(max(x[3] + c @ c, 1e-12))


LIMBUS_D = 0.085   # texture-space iris radius used by CharacterModel.ApplyEyes (fade 0.075..0.095)
PUPIL_D = 0.032


def eye_uv(theta, phi, theta_l):
    t = np.asarray(theta)
    d = np.where(t <= theta_l * 1.15, LIMBUS_D * t / theta_l,
                 LIMBUS_D * 1.15 + (t - theta_l * 1.15) / (math.pi - theta_l * 1.15) * (0.47 - LIMBUS_D * 1.15))
    return 0.5 + d * np.sin(phi) * 0.5, 0.5 + d * np.cos(phi)


def rebuild_eyes(ctx, eye_obj, rings=15, segs=24):
    """Replace the MakeHuman eye mesh (eyeball + transparent cornea shells) by two opaque eyeballs with a corneal
    bulge. Keeps the object (name, parent, material slot) and gives it weights + morph shapes."""
    me = eye_obj.data
    co = np.array([v.co[:] for v in me.vertices])
    comps = _components(me)
    rig = ctx.rig
    new_v, new_f, new_uv, side_of = [], [], [], []
    for sgn, bone in ((1, "LeftEye"), (-1, "RightEye")):
        cs = [c for c in comps if np.sign(co[c].mean(0)[0]) == sgn]
        # eyeball = the component with the smaller fitted radius (the cornea shell is larger)
        fits = [(_fit_sphere(co[c]), c) for c in cs]
        (c0, R), comp = min(fits, key=lambda f: f[0][1])
        fwd = nrm(ctx.T[bone] - ctx.L[bone])
        up0 = nrm(np.array((0, 0, 1.0)) - fwd * fwd[2])
        rt = np.cross(fwd, up0)
        theta_l = math.asin(min(0.98, 0.00575 / R)) if R > 0.006 else math.radians(28)
        base = len(new_v)
        grid = []
        thetas = list(np.linspace(0, theta_l * 0.6, 3)[1:]) + list(np.linspace(theta_l * 0.8, theta_l * 1.15, 3)) + list(np.linspace(theta_l * 1.35, math.pi * 0.92, rings - 5))
        new_v.append(c0 + fwd * (R + 0.0007)); new_uv.append((0.5, 0.5))
        for th in thetas:
            row = []
            bulge = 0.0007 * max(0.0, math.cos(min(th / (theta_l * 1.1), 1.0) * math.pi / 2)) ** 1.2
            for k in range(segs):
                ph = 2 * math.pi * k / segs
                d = fwd * math.cos(th) + (up0 * math.cos(ph) + rt * math.sin(ph)) * math.sin(th)
                row.append(len(new_v))
                new_v.append(c0 + d * (R + bulge))
                u, v = eye_uv(th, ph, theta_l)
                new_uv.append((float(u), float(v)))
            grid.append(row)
        for k in range(segs):
            new_f.append([base, grid[0][k], grid[0][(k + 1) % segs]])
        for i in range(len(grid) - 1):
            for k in range(segs):
                k2 = (k + 1) % segs
                new_f.append([grid[i][k], grid[i + 1][k], grid[i + 1][k2], grid[i][k2]])
        side_of += [bone] * (len(new_v) - base)
        try:
            n0 = len(new_v)
            _lid_details(ctx, c0, R, fwd, up0, rt, new_v, new_f, new_uv)
            side_of += ["Head"] * (len(new_v) - n0)
        except Exception as e:
            print("EYE details skipped:", e)
    bm = bmesh.new()
    vs = [bm.verts.new(Vector(p)) for p in new_v]
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in new_f:
        face = bm.faces.new([vs[i] for i in f])
        for loop, i in zip(face.loops, f):
            loop[uvl].uv = new_uv[i]
        face.smooth = True
    mats = list(me.materials)
    newme = bpy.data.meshes.new(eye_obj.name)
    bm.to_mesh(newme)
    bm.free()
    for m in mats:
        newme.materials.append(m)
    eye_obj.shape_key_clear() if eye_obj.data.shape_keys else None
    old = eye_obj.data
    eye_obj.data = newme
    bpy.data.meshes.remove(old)
    for g in list(eye_obj.vertex_groups):
        eye_obj.vertex_groups.remove(g)
    for bone in ("LeftEye", "RightEye", "Head"):
        ids = [i for i, b in enumerate(side_of) if b == bone]
        if ids:
            eye_obj.vertex_groups.new(name="mixamorig:" + bone).add(ids, 1.0, "REPLACE")
    # morph shapes from the body (eyes do not follow lid/mouth expressions)
    P = np.array(new_v)
    bind = SurfaceBinding(ctx.body, ctx.basis, P, max_dist=0.3)
    for name, sco in ctx.B.shapes.items():
        if name.startswith("x_"):
            continue
        dlt = bind.transfer(sco - ctx.basis)
        # keep eyeballs rigid per eye: average the delta of each eye
        for bone in ("LeftEye", "RightEye"):
            idx = [i for i, b in enumerate(side_of) if b == bone]
            dlt[idx] = dlt[idx].mean(0)
        if np.abs(dlt).max() > 1e-5:
            add_shape_key(eye_obj, name, P + dlt)
    return eye_obj


def _lid_details(ctx, c0, R, fwd, up0, rt, V, F, UV):
    """Tear line (wet meniscus strip on the eyeball along the lower lid margin) and caruncle (pink tear-duct mound
    in the inner corner). UVs point at dedicated texels in the eye texture corners."""
    co = ctx.basis
    head = ctx.region["head"] > 0.5
    d = co - c0
    dist = np.linalg.norm(d, axis=1)
    dirs = d / np.maximum(dist[:, None], 1e-9)
    cand = head & (dist > R + 0.0002) & (dist < R + 0.0045) & ((dirs @ fwd) > 0.25)
    pts = co[cand]
    if len(pts) < 8:
        return
    q = pts - c0
    upc = q @ up0
    ang = np.arctan2(upc, q @ rt)
    lower = upc < -0.001
    lp, la = pts[lower], ang[lower]
    if len(lp) < 5:
        return
    bins = np.linspace(la.min(), la.max(), 11)
    margin = []
    for k in range(10):
        m = (la >= bins[k]) & (la <= bins[k + 1])
        if m.any():
            margin.append(lp[m].mean(0))
    base = len(V)
    for i, p in enumerate(margin):
        dp = nrm(p - c0)
        V.append(c0 + dp * (R + 0.00025))
        V.append(c0 + nrm(dp + up0 * 0.085) * (R + 0.0004))
        uu = 0.09 + 0.08 * i / max(len(margin) - 1, 1)
        UV.append((uu, 0.012)); UV.append((uu, 0.035))
    for i in range(len(margin) - 1):
        a = base + i * 2
        F.append([a, a + 2, a + 3, a + 1])
    # caruncle at the medial end (closest to the nose)
    mid = np.abs(upc) < 0.0025
    if mid.any():
        mp = pts[mid][np.argmin(np.abs(pts[mid][:, 0]))]
        cc = c0 + nrm(mp - c0) * (R + 0.0004)
        rr = 0.0016
        b0 = len(V)
        rings, segs = 4, 6
        V.append(cc + fwd * rr * 0.7); UV.append((0.035, 0.035))
        for i in range(1, rings + 1):
            th = math.pi * i / (rings + 1)
            for k in range(segs):
                ph = 2 * math.pi * k / segs
                dv = fwd * math.cos(th) + (up0 * math.cos(ph) + rt * math.sin(ph)) * math.sin(th)
                V.append(cc + dv * rr * np.array((1.0, 1.0, 0.8)))
                UV.append((0.02 + 0.03 * k / segs, 0.015 + 0.03 * i / rings))
        V.append(cc - fwd * rr * 0.7); UV.append((0.035, 0.035))
        for k in range(segs):
            F.append([b0, b0 + 1 + k, b0 + 1 + (k + 1) % segs])
        for i in range(rings - 1):
            for k in range(segs):
                a = b0 + 1 + i * segs
                F.append([a + k, a + segs + k, a + segs + (k + 1) % segs, a + (k + 1) % segs])
        last = b0 + 1 + rings * segs
        a = b0 + 1 + (rings - 1) * segs
        for k in range(segs):
            F.append([a + (k + 1) % segs, a + k, last])


def eye_textures(out_dir, size=1024, seed=11):
    """Eye_grey/brown/blue/green.png in the centred-iris layout."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size; v = (yy + 0.5) / size
    dx = (u - 0.5) * 2.0; dy = v - 0.5            # undo the 2x u compression -> isotropic eye-space
    d = np.hypot(dx, dy)
    ang = np.arctan2(dx, dy)
    # Sclera: warm off-white, pinker towards the corners, fine veins
    scl = np.stack([np.full_like(d, 0.92), np.full_like(d, 0.88), np.full_like(d, 0.84)], -1)
    edge = ss(0.12, 0.42, d)
    scl = scl * (1 - 0.18 * edge[..., None]) + np.array((0.12, 0.02, 0.0)) * edge[..., None] * 0.6
    vein = np.zeros_like(d)
    for _ in range(46):
        a0 = rng.uniform(-math.pi, math.pi)
        r0 = rng.uniform(0.3, 0.46)
        pts = [(math.sin(a0) * r0, math.cos(a0) * r0)]
        for k in range(14):
            px, py = pts[-1]
            dirr = -np.array((px, py)) / math.hypot(px, py)
            j = rng.normal(0, 0.6, 2)
            step = (dirr + j) * 0.012
            pts.append((px + step[0], py + step[1]))
            if math.hypot(*pts[-1]) < LIMBUS_D * 1.35:
                break
        for (ax_, ay_), (bx_, by_) in zip(pts[:-1], pts[1:]):
            dd, _ = TB.line_sdf2(dx, dy, ax_, ay_, bx_, by_)
            vein = np.maximum(vein, np.exp(-(dd / 0.0016) ** 2) * ss(0.12, 0.3, d) * rng.uniform(0.3, 0.8))
    scl = scl * (1 - vein[..., None] * np.array((0.15, 0.55, 0.55)))
    # Iris (luminance pattern; Unity tints it): radial fibres, crypts, collarette, dark limbal ring
    r = d / LIMBUS_D
    fib = 0.5 + 0.3 * np.sin(ang * 90 + 3 * np.sin(ang * 7)) + 0.2 * np.sin(ang * 151 + r * 13) + 0.15 * np.sin(ang * 37 + r * 9)
    crypt = TB.fbm3(np.stack([dx * 40, dy * 40, np.zeros_like(dx)], -1).reshape(-1, 3), 1.0, 3, 2.0).reshape(d.shape)
    iris_l = 0.42 + 0.22 * fib * (0.6 + 0.4 * r) + 0.15 * crypt
    coll = np.exp(-((r - 0.52) / 0.07) ** 2)
    iris_l = iris_l * (1 + 0.35 * coll) * (1 - 0.55 * ss(0.78, 1.0, r))
    pupil = 1 - ss(PUPIL_D / LIMBUS_D - 0.04, PUPIL_D / LIMBUS_D + 0.02, r)
    iris_l = iris_l * (1 - pupil) + 0.02 * pupil
    in_iris = 1 - ss(0.97, 1.06, r)
    limbal = np.exp(-((r - 1.0) / 0.09) ** 2)
    lid = 1 - 0.2 * ss(0.03, 0.17, dy) - 0.06 * ss(0.12, 0.3, np.abs(dx))       # upper lid / lash shadow, corners
    car = (u < 0.07) & (v < 0.07)
    tear = (u > 0.08) & (u < 0.18) & (v < 0.05)
    out = {}
    tints = {"grey": (0.55, 0.57, 0.6), "brown": (0.42, 0.26, 0.13), "blue": (0.28, 0.42, 0.62), "green": (0.32, 0.45, 0.25)}
    for name, t in tints.items():
        iris_rgb = iris_l[..., None] * np.array(t) * 2.0
        if name == "brown":
            iris_rgb = iris_rgb * (1 + 0.4 * coll[..., None] * np.array((0.6, 0.4, 0.0)))
        col = scl * (1 - in_iris[..., None]) + iris_rgb * in_iris[..., None]
        col = col * (1 - 0.6 * limbal[..., None])
        col = col * lid[..., None]
        col[car] = np.array((0.78, 0.47, 0.46)) * (0.9 + 0.1 * np.sin(xx[car] * 0.9))[:, None]
        col[tear] = np.array((0.96, 0.9, 0.88))
        col = np.clip(col, 0, 1)
        TB.write_png(col, os.path.join(out_dir, f"Eye_{name}.png"), "RGB")
        out[name] = f"Eye_{name}.png"
    return out


# ----------------------------------------------------------------------------- decimation with blendshapes


def decimate_with_shapes(obj, ratio, ctx=None):
    """Decimate obj and rebuild weights and shape keys by binding the new vertices to the original surface."""
    me = obj.data
    if not me.shape_keys:
        m = obj.modifiers.new("dec", "DECIMATE"); m.ratio = ratio
        gear.apply_modifiers(obj)
        return obj
    kb = me.shape_keys.key_blocks
    basis = np.array([v.co[:] for v in kb[0].data])
    shapes = {k.name: np.array([v.co[:] for v in k.data]) for k in kb[1:]}
    groups = {g.index: g.name for g in obj.vertex_groups}
    W = {}
    for v in me.vertices:
        for g in v.groups:
            W.setdefault(groups[g.group], np.zeros(len(me.vertices)))[v.index] = g.weight
    me.calc_loop_triangles()
    src_faces = [list(t.vertices) for t in me.loop_triangles]    # triangles: n-gons safe
    tree = BVHTree.FromPolygons([Vector(c) for c in basis], src_faces)
    obj.shape_key_clear()
    mods = [(m.name, m.type, getattr(m, "object", None)) for m in obj.modifiers]
    obj.modifiers.clear()
    m = obj.modifiers.new("dec", "DECIMATE"); m.ratio = ratio
    gear.apply_modifiers(obj)
    co = np.array([v.co[:] for v in obj.data.vertices])
    I, Wt = [], []
    from mathutils.interpolate import poly_3d_calc
    for p in co:
        loc, n, fi, d = tree.find_nearest(Vector(p))
        vids = src_faces[fi]
        w = poly_3d_calc([Vector(basis[v]) for v in vids], loc)
        I.append(vids + [vids[0]] * (4 - len(vids))); Wt.append(list(w) + [0.0] * (4 - len(vids)))
    I = np.array(I); Wt = np.array(Wt)
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    for name, arr in W.items():
        w = (arr[I] * Wt).sum(1)
        vg = obj.vertex_groups.new(name=name)
        for i in np.where(w > 0.01)[0]:
            vg.add([int(i)], float(w[i]), "REPLACE")
    for name, sco in shapes.items():
        d = ((sco - basis)[I] * Wt[..., None]).sum(1)
        if np.abs(d).max() > 1e-6:
            add_shape_key(obj, name, co + d)
    for (n, t, o) in mods:
        if t == "ARMATURE":
            mm = obj.modifiers.new(n, "ARMATURE"); mm.object = o
    return obj


# ----------------------------------------------------------------------------- body UV relayout


def relayout_body(body, head_weight=1.5):
    """Copy the MakeHuman UVs to 'UVOld', then shelf-pack the remaining Body islands into 0..1 (head islands get
    `head_weight` x the texel density of the rest)."""
    me = body.data
    old = me.uv_layers.active
    data = np.empty(len(me.loops) * 2); old.data.foreach_get("uv", data)
    if "UVOld" not in me.uv_layers:
        lay = me.uv_layers.new(name="UVOld")
        lay.data.foreach_set("uv", data)
    me.uv_layers.active = me.uv_layers[old.name] if old.name != "UVOld" else me.uv_layers[0]
    me.uv_layers[old.name].active_render = True
    # Island weights: the MakeHuman head occupies u > 0.6 in the old layout.
    TB.pack_weighted(body, "Skin", lambda faces, uv: head_weight if uv[:, 0].mean() > 0.6 and uv[:, 1].mean() > 0.12 else 1.0,
                     margin=0.004)
    return body


# ----------------------------------------------------------------------------- tattoos (2-D pattern library)


class Pattern:
    """Line drawing in a 2-D parameter space (metres). Accumulates (distance, colour index) for evaluation."""

    def __init__(self):
        self.segs = []   # (ax, ay, bx, by, width, color_index, taper)
        self.dots = []   # (x, y, radius, ring_width, color_index)

    def line(self, pts, w=0.0012, c=0, taper=False):
        for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
            tw = (w, w * 0.35) if taper and i == len(pts) - 2 else (w, w)
            self.segs.append((a[0], a[1], b[0], b[1], tw, c))

    def via(self, x, y, r=0.0022, ring=0.0008, c=0):
        self.dots.append((x, y, r, ring, c))

    def trace(self, rng, start, heading, n, step=(0.006, 0.016), w=0.0011, c=0, bounds=None, turn=0.45):
        """Manhattan/45-degree circuit trace random walk ending in a via."""
        pts = [np.array(start, float)]
        hd = heading
        for _ in range(n):
            if rng.random() < turn:
                hd += rng.choice([-1, 1]) * math.pi / 4
            p = pts[-1] + np.array((math.cos(hd), math.sin(hd))) * rng.uniform(*step)
            if bounds is not None and not (bounds[0] <= p[0] <= bounds[1] and bounds[2] <= p[1] <= bounds[3]):
                break
            pts.append(p)
        self.line(pts, w, c)
        self.via(pts[-1][0], pts[-1][1], 0.0019, 0.0007, c)
        return pts

    def spike(self, a, b, w=0.004, c=0, bend=0.3):
        """Tech-tribal tapered spike from a to b (curved)."""
        a = np.asarray(a, float); b = np.asarray(b, float)
        n = 8
        perp = np.array((-(b - a)[1], (b - a)[0]))
        pts = [a + (b - a) * t + perp * bend * math.sin(t * math.pi) * 0.3 for t in np.linspace(0, 1, n)]
        for i in range(n - 1):
            w0 = w * (1 - i / (n - 1)) + 0.0004
            w1 = w * (1 - (i + 1) / (n - 1)) + 0.0004
            self.segs.append((pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], (w0, w1), c))

    def eval(self, X, Y, ncol=2, soft=0.00035):
        """Returns per-colour coverage (ncol, N) for points (X, Y)."""
        cov = np.zeros((ncol, len(X)), np.float32)
        for (ax, ay, bx, by, (w0, w1), c) in self.segs:
            mnx, mxx = min(ax, bx) - w0, max(ax, bx) + w0
            mny, mxy = min(ay, by) - w0, max(ay, by) + w0
            sel = np.where((X > mnx) & (X < mxx) & (Y > mny) & (Y < mxy))[0]
            if len(sel) == 0:
                continue
            d, t = TB.line_sdf2(X[sel], Y[sel], ax, ay, bx, by)
            w = (w0 + (w1 - w0) * t) * 0.5
            cov[c, sel] = np.maximum(cov[c, sel], 1 - ss(w - soft, w + soft, d))
        for (x, y, r, ring, c) in self.dots:
            sel = np.where((np.abs(X - x) < r + ring) & (np.abs(Y - y) < r + ring))[0]
            if len(sel) == 0:
                continue
            d = np.hypot(X[sel] - x, Y[sel] - y)
            v = np.maximum(1 - ss(ring * 0.5 - soft, ring * 0.5 + soft, np.abs(d - r + ring * 0.5)), 1 - ss(r * 0.35, r * 0.35 + soft * 2, d))
            cov[c, sel] = np.maximum(cov[c, sel], v)
        return cov


# ----------------------------------------------------------------------------- face landmarks


def face_landmarks(ctx):
    L = ctx.L
    co = ctx.basis
    head = ctx.region["head"] > 0.5
    eyeL, eyeR = L["LeftEye"], L["RightEye"]
    em = (eyeL + eyeR) * 0.5
    front = head & (co[:, 1] < em[1] + 0.02) & (np.abs(co[:, 0]) < 0.03)
    def most_forward(z0, z1):
        sel = front & (co[:, 2] > z0) & (co[:, 2] < z1)
        i = np.where(sel)[0]
        return co[i[np.argmin(co[i, 1])]] if len(i) else em + np.array((0, -0.05, -0.05))
    nose = most_forward(em[2] - 0.06, em[2] - 0.015)
    mouth = most_forward(em[2] - 0.095, em[2] - 0.065)
    chin = most_forward(em[2] - 0.15, em[2] - 0.11)
    return {"eyeL": eyeL, "eyeR": eyeR, "eyeM": em, "nose": nose, "mouth": mouth, "chin": chin}


# ----------------------------------------------------------------------------- tattoo designs


def _forearm_space(L, side, P):
    el, wr = (L["LeftForeArm"], L["LeftHand"]) if side > 0 else (L["RightForeArm"], L["RightHand"])
    t, phi, rad = gear.limb_coords(P, wr, el, (0, 0, 1))
    return t, phi * 0.042, rad


def tattoo_regions(cid, ctx, FL):
    """Returns list of (region_fn(P) -> (X, Y, mask), Pattern, palette) for a character."""
    L = ctx.L
    rng = np.random.default_rng({"kael": 7, "lyra": 9, "mira": 13, "tomas": 17}.get(cid, 1))
    regs = []
    if cid == "kael":
        cyan, mag = (0.0, 0.9, 1.0), (1.0, 0.17, 0.84)
        # right forearm, inner (skin-visible) side: spine + circuit branches + tribal spikes
        pat = Pattern()
        flen = np.linalg.norm(L["RightForeArm"] - L["RightHand"])
        c = 0.042 * math.radians(130)
        pat.line([(0.02, c), (flen * 0.35, c + 0.004), (flen * 0.6, c - 0.003), (flen * 0.92, c + 0.002)], 0.0016, 0)
        for k in range(9):
            t0 = 0.035 + k * flen * 0.095
            pat.trace(rng, (t0, c), math.pi / 2 * rng.choice([-1, 1]) + rng.uniform(-0.3, 0.3), 5, (0.005, 0.012), 0.001,
                      1 if k % 3 == 1 else 0, (0.0, flen, c - 0.04, c + 0.04))
        for k in range(4):
            t0 = flen * (0.25 + 0.17 * k)
            pat.spike((t0, c + 0.003), (t0 + 0.03, c + 0.022), 0.0035, 0, 0.5)
            pat.spike((t0 + 0.01, c - 0.003), (t0 + 0.04, c - 0.02), 0.003, 0, -0.5)
        pat.via(0.012, c, 0.0032, 0.001, 1)
        regs.append((lambda P: (lambda t, s, r: (t, s, (np.sign(P[:, 0]) < 0) & (t > -0.01) & (t < flen + 0.02) & (r < 0.08)))(*_forearm_space(L, -1, P)), pat, (cyan, mag)))
        # right side of the neck up to behind the right ear
        pat2 = Pattern()
        nk = L["Neck"]
        def neck_space(P):
            d = P - np.array((0, nk[1] + 0.01, 0))
            az = np.arctan2(-d[:, 0], -d[:, 1])  # +: towards the character's right
            return az * 0.065, P[:, 2], (np.abs(d[:, 0]) > 0.0) & (P[:, 2] > 1.5) & (P[:, 2] < 1.82) & (az > 0.3) & (az < 2.6)
        z0 = nk[2] - 0.05
        spine = [(0.075, z0), (0.08, z0 + 0.04), (0.092, z0 + 0.08), (0.11, z0 + 0.12), (0.125, z0 + 0.155), (0.13, z0 + 0.19)]
        pat2.line(spine, 0.0015, 0)
        for k in range(6):
            p0 = spine[k % len(spine)]
            pat2.trace(rng, p0, rng.choice([0.0, math.pi]) + rng.uniform(-0.4, 0.4), 4, (0.004, 0.01), 0.0009, 1 if k == 2 else 0)
        for k in range(3):
            pat2.spike((0.085 + 0.012 * k, z0 + 0.03 + 0.04 * k), (0.06 + 0.012 * k, z0 + 0.06 + 0.04 * k), 0.003, 0, 0.4)
        pat2.via(spine[-1][0], spine[-1][1], 0.0028, 0.0009, 1)
        regs.append((neck_space, pat2, (cyan, mag)))
        # thin line along the left temple implant
        pat3 = Pattern()
        em = FL["eyeM"]
        def temple_space(P):
            return P[:, 1], P[:, 2], (P[:, 0] > 0.05) & (P[:, 2] > em[2] + 0.01) & (P[:, 2] < em[2] + 0.075) & (P[:, 1] < em[1] + 0.12)
        y0, z_ = em[1] + 0.025, em[2] + 0.03
        pat3.line([(y0 - 0.005, z_ + 0.012), (y0 + 0.02, z_ + 0.016), (y0 + 0.045, z_ + 0.01), (y0 + 0.065, z_ - 0.008)], 0.0009, 0)
        pat3.via(y0 + 0.065, z_ - 0.008, 0.0016, 0.0006, 1)
        regs.append((temple_space, pat3, (cyan, mag)))
    elif cid == "lyra":
        mag, vio = (1.0, 0.17, 0.84), (0.55, 0.36, 1.0)
        # collarbones: delicate traces along each clavicle
        pat = Pattern()
        sh = L["LeftShoulder"]
        def chest_space(P):
            return P[:, 0], P[:, 2], (P[:, 1] < -0.03) & (P[:, 2] > sh[2] - 0.08) & (P[:, 2] < sh[2] + 0.06) & (np.abs(P[:, 0]) < 0.2)
        zc = sh[2] - 0.015
        for s_ in (1, -1):
            pts = [(s_ * 0.025, zc - 0.012), (s_ * 0.06, zc - 0.004), (s_ * 0.1, zc + 0.002), (s_ * 0.14, zc + 0.004)]
            pat.line(pts, 0.0009, 0)
            for k in range(3):
                pat.trace(rng, pts[k + 1], -math.pi / 2 + rng.uniform(-0.5, 0.5), 3, (0.004, 0.008), 0.0007, 1 if k == 1 else 0)
        pat.via(0.0, zc - 0.022, 0.0024, 0.0008, 0)
        regs.append((chest_space, pat, (mag, vio)))
        # left side of the neck
        pat2 = Pattern()
        nk = L["Neck"]
        def neck_space(P):
            d = P - np.array((0, nk[1] + 0.01, 0))
            az = np.arctan2(d[:, 0], -d[:, 1])
            return az * 0.055, P[:, 2], (P[:, 2] > nk[2] - 0.07) & (P[:, 2] < nk[2] + 0.11) & (az > 0.4) & (az < 2.4)
        z0 = nk[2] - 0.05
        sp = [(0.07, z0), (0.075, z0 + 0.05), (0.085, z0 + 0.1), (0.09, z0 + 0.14)]
        pat2.line(sp, 0.0009, 0)
        for k in range(4):
            pat2.trace(rng, sp[k % 4], rng.choice([0, math.pi]), 3, (0.003, 0.007), 0.0007, k % 2)
        regs.append((neck_space, pat2, (mag, vio)))
        # both forearms
        for s_ in (1, -1):
            patf = Pattern()
            flen = np.linalg.norm(L["LeftForeArm"] - L["LeftHand"])
            c = 0.042 * math.radians(170)
            patf.line([(0.03, c), (flen * 0.5, c + 0.003), (flen * 0.85, c)], 0.001, 0)
            for k in range(7):
                patf.trace(rng, (0.04 + k * flen * 0.11, c), math.pi / 2 * rng.choice([-1, 1]), 4, (0.004, 0.009), 0.0008, 1 if k % 3 == 0 else 0,
                           (0.0, flen, c - 0.035, c + 0.035))
            regs.append(((lambda s__: (lambda P: (lambda t, s, r: (t, s, (np.sign(P[:, 0]) == s__) & (t > -0.01) & (t < flen + 0.02) & (r < 0.07)))(*_forearm_space(L, s__, P))))(s_), patf, (mag, vio)))
        # small glyph under the left eye (abstract, no letters)
        patg = Pattern()
        e = FL["eyeL"]
        def eye_space(P):
            return P[:, 0], P[:, 2], (P[:, 0] > 0.0) & (P[:, 1] < e[1] + 0.01) & (np.abs(P[:, 2] - (e[2] - 0.03)) < 0.025)
        gx, gz = e[0] + 0.006, e[2] - 0.026
        patg.line([(gx - 0.006, gz), (gx + 0.004, gz)], 0.0007, 0)
        patg.line([(gx - 0.003, gz - 0.004), (gx + 0.007, gz - 0.004)], 0.0007, 1)
        patg.via(gx + 0.009, gz - 0.002, 0.0011, 0.0005, 0)
        regs.append((eye_space, patg, (mag, vio)))
    elif cid == "mira":
        amber, teal = (1.0, 0.62, 0.25), (0.25, 0.95, 0.85)
        pat = Pattern()
        hd = L["Head"]
        def nape_space(P):
            d = P - np.array((0, hd[1], 0))
            az = np.arctan2(d[:, 0], -d[:, 1])
            return az * 0.06, P[:, 2], (P[:, 2] > hd[2] - 0.13) & (P[:, 2] < hd[2] + 0.02) & (az > 0.7) & (az < 1.7)
        for k in range(5):
            pat.trace(rng, (0.06 + 0.008 * k, hd[2] - 0.11 + k * 0.022), math.pi / 2 + rng.uniform(-0.4, 0.4), 4, (0.004, 0.009), 0.0009, k % 2)
        regs.append((nape_space, pat, (teal, amber)))
        for s_ in (1, -1):
            hp = Pattern()
            hand = L["LeftHand"] if s_ > 0 else L["RightHand"]
            def hand_space(P, hand=hand, s_=s_):
                d = P - hand
                return d[:, 0] * s_ + d[:, 1] * 0.3, d[:, 2] + d[:, 1] * 0.3, (np.sign(P[:, 0]) == s_) & (np.linalg.norm(d, axis=1) < 0.09) & (d[:, 2] > -0.02)
            hp.line([(0.0, 0.0), (0.02, 0.01), (0.045, 0.012)], 0.0011, 0)
            for k in range(3):
                hp.trace(rng, (0.012 * k, 0.003 * k), rng.uniform(-1, 1), 3, (0.004, 0.008), 0.0008, 1)
            regs.append((hand_space, hp, (teal, amber)))
    elif cid == "tomas":
        lime, cyan = (0.6, 1.0, 0.35), (0.0, 0.9, 1.0)
        pat = Pattern()
        em = FL["eyeM"]
        def head_side(P):
            return P[:, 1], P[:, 2], (P[:, 0] < -0.04) & (P[:, 2] > em[2] + 0.0) & (P[:, 2] < em[2] + 0.12)
        for k in range(7):
            pat.trace(rng, (em[1] + 0.03 + k * 0.012, em[2] + 0.03 + (k % 3) * 0.012), rng.choice([math.pi / 2, 0.0, math.pi]), 5, (0.005, 0.011), 0.0012, 1 if k % 3 == 0 else 0)
        regs.append((head_side, pat, (lime, cyan)))
    return regs


def eval_tattoos(regs, P):
    """Returns (emission rgb (N,3), coverage (N,))."""
    rgb = np.zeros((len(P), 3), np.float32)
    cov = np.zeros(len(P), np.float32)
    for fn, pat, pal in regs:
        X, Y, m = fn(P)
        idx = np.where(m)[0]
        if len(idx) == 0:
            continue
        cv = pat.eval(X[idx], Y[idx], len(pal))
        for ci, col in enumerate(pal):
            rgb[idx] = np.maximum(rgb[idx], cv[ci][:, None] * np.array(col))
            cov[idx] = np.maximum(cov[idx], cv[ci])
    return rgb, cov


# ----------------------------------------------------------------------------- skin textures


TONES = {
    "male": {"light": "young_caucasian_male", "medium": "toigo_light_skin_male_bronze", "tan": "young_asian_male", "dark": "young_african_male"},
    "female": {"light": "young_caucasian_female", "medium": "toigo_light_skin_female_bronze", "tan": "young_asian_female", "dark": "young_african_female"},
}


def _skin_png(folder):
    d = os.path.join(MPFB_DATA, "skins", folder)
    f = [x for x in os.listdir(d) if x.lower().endswith(".png") and "nrm" not in x.lower() and "spec" not in x.lower()]
    return os.path.join(d, f[0])


def skin_textures(body, ctx, cid, gender, out_dir, size=2048, tones=None, beard=0.0, scalp=None, hide=(), tattoo=True, samples=48):
    """Writes Skin_<tone>.png, Skin_Normal.png, Skin_MaskMap.png, Skin_Tattoo.png (+Mask), Skin_Stubble.png."""
    tones = tones or TONES[gender]
    FL = face_landmarks(ctx)
    L = ctx.L
    # Skin AO is body self-occlusion only. Garments, armour, hair and especially the (optional, usually hidden) beard /
    # brow / lash cards must not be in the bake: sparse alpha cards baked as opaque geometry produced the speckled,
    # mottled jaw and neck in Unity, and garment shells blackened the skin at every cuff and collar.
    keep = {body.name} | {o.name for o in bpy.data.objects if o.type == "MESH" and o.name.split(".")[0] in ("Eyes",)}
    hide_all = [o for o in bpy.data.objects if o.type in ("MESH", "CURVES", "CURVE") and o.name not in keep]
    ao = TB.bake_ao([body], "Skin", size, samples=max(samples, 128), distance=0.03, hide=hide_all)
    ao = TB.blur(ao, 4)   # denoise: the occlusion map must not carry sampling speckle into URP
    ao = 1.0 - (1.0 - np.clip(ao, 0, 1)) * 0.8   # never fully black (URP occlusion strength stacks on top)
    T = TB.raster([body], "Skin", size, attrs=("rhead", "rhand", "rneck"), uv2="UVOld")
    idx = np.where(T.cov)[0]
    P = T.P[idx].astype(np.float64); N = T.N[idx].astype(np.float64)
    uvo = T.UV2[idx].astype(np.float64)
    ao_t = ao.reshape(-1)[idx]
    rhead, rhand = T.A["rhead"][idx], T.A["rhand"][idx]
    em, nose, mouth, chin = FL["eyeM"], FL["nose"], FL["mouth"], FL["chin"]
    face = (rhead > 0.5) & (P[:, 1] < em[1] + 0.035)

    def blob(c, r):
        return np.exp(-np.sum((P - c) ** 2, 1) / (r * r))
    cheeks = blob(np.array((0.045, em[1] - 0.005, em[2] - 0.04)), 0.026) + blob(np.array((-0.045, em[1] - 0.005, em[2] - 0.04)), 0.026)
    nose_b = blob(nose, 0.018)
    lips = blob(mouth + np.array((0, 0.006, 0)), 0.016)
    lips_core = np.exp(-((P[:, 2] - mouth[2]) / 0.008) ** 2) * np.exp(-((P[:, 0]) / 0.024) ** 2) * (P[:, 1] < mouth[1] + 0.012)
    ears = (rhead > 0.5) & (np.abs(P[:, 0]) > 0.065) & (np.abs(P[:, 2] - em[2]) < 0.04) & (P[:, 1] > em[1] + 0.05)
    forehead = face & (P[:, 2] > em[2] + 0.025)
    tzone = np.clip(blob(np.array((0, em[1] - 0.01, em[2] + 0.045)), 0.03) + nose_b + blob(chin, 0.015) * 0.5, 0, 1)
    # beard zone (jaw, chin, upper lip, lower cheeks)
    jaw = (rhead > 0.5) & (P[:, 2] < em[2] - 0.045) & (P[:, 1] < em[1] + 0.07)
    beard_m = jaw * (1 - ss(0.035, 0.012, np.abs(P[:, 2] - mouth[2]) + np.maximum(0, 0.024 - np.abs(P[:, 0])) * 0)) * 0 + jaw
    beard_m = beard_m * (1 - lips_core * 1.0) * (1 - ss(em[2] - 0.05, em[2] - 0.035, P[:, 2]) * 0)
    beard_m = np.clip(beard_m * ss(em[2] - 0.035, em[2] - 0.06, P[:, 2]) + jaw * ss(0.0, 0.01, -(P[:, 2] - (mouth[2] + 0.012))) * (np.abs(P[:, 0]) < 0.025) * 0.8, 0, 1)
    # feather the shadow zone in texture space (the region tests above are hard-edged -> visible painted border)
    bm_img = TB.dilate(_full(T, idx, beard_m), T.cov.reshape(T.size, T.size), 16)
    beard_m = np.clip(TB.blur(bm_img, 14).reshape(-1)[idx], 0, 1)
    # scalp shadow under hair
    if scalp is not None:
        sc_m = scalp(P)
    else:
        sc_m = np.zeros(len(P))
    # ---- height (metres): pores, wrinkles, micro detail
    # pores at >= 3 texels per cell and shallow: at 1.1 mm / 42 um they aliased into a speckled, scaly pattern in URP
    cell = TB.worley3(P, 1.0 / 0.0017, 3.0)
    pore_scale = 1.0 + 0.6 * np.clip(cheeks + nose_b, 0, 1)
    pores = (1 - ss(0.0, 0.32 * pore_scale, cell))
    h = -0.000011 * pores * (0.6 + 0.4 * face)
    h += 0.000007 * TB.fbm3(P, 600.0, 3, 1.0)
    # skin micro-relief: two crossing families of fine lines (dermatoglyphic texture), strongest off the face
    ml = np.minimum(np.abs(np.sin((P[:, 0] + P[:, 2]) / 0.0009 * math.pi)), np.abs(np.sin((P[:, 0] - P[:, 2] + P[:, 1]) / 0.0011 * math.pi)))
    h -= 0.000004 * ss(0.16, 0.06, ml) * (1 - face)
    # forehead lines
    fl = np.sin((P[:, 2] - em[2]) / 0.0055 * 2 * math.pi + 0.8 * TB.fbm3(P, 40, 2, 2.0)) * forehead * ss(0.6, 0.0, np.abs(P[:, 0]) / 0.05)
    h -= 0.00009 * np.clip(fl, 0, 1) * (0.5 + 0.5 * TB.fbm3(P, 30, 2, 5.0))
    # crow's feet
    for e in (FL["eyeL"], FL["eyeR"]):
        corner = e + np.array((np.sign(e[0]) * 0.02, -0.005, 0.0))
        d = P - corner
        ang = np.arctan2(d[:, 2], np.abs(d[:, 0]))
        rr = np.hypot(d[:, 0], d[:, 2])
        cf = (np.abs(np.sin(ang * 9)) < 0.2) * ss(0.004, 0.008, rr) * (1 - ss(0.016, 0.024, rr)) * (np.sign(d[:, 0]) == np.sign(e[0]))
        h -= 0.00007 * cf
    # lip vertical lines
    h -= 0.00004 * ss(0.3, 0.1, np.abs(np.sin(P[:, 0] / 0.0016 * math.pi))) * lips_core
    # neck rings and knuckle creases
    neck = (T.A["rneck"][idx] > 0.4)
    h -= 0.00004 * neck * ss(0.22, 0.05, np.abs(np.sin(P[:, 2] / 0.012 * math.pi + 2 * TB.fbm3(P, 30, 2, 9))))
    h -= 0.00008 * (rhand > 0.5) * ss(0.55, 0.75, TB.fbm3(P * np.array((1, 1, 6)), 140, 2, 4.0) * 0.5 + 0.5)
    Hn = TS_normal(T, idx, h)
    # ---- mask map
    smooth = 0.28 + 0.12 * tzone + 0.18 * lips_core + 0.03 * face - 0.02 * pores
    smooth = np.clip(smooth - 0.04 * sc_m, 0.15, 0.7)
    thick = np.clip(ears * 1.0 + nose_b * 0.6 + rhand * 0.2, 0, 1)
    MM = np.stack([np.zeros_like(smooth), np.clip(ao_t, 0, 1), thick, smooth], 1)
    # ---- tattoos
    regs = tattoo_regions(cid, ctx, FL) if tattoo else []
    trgb, tcov = eval_tattoos(regs, P)
    # ---- albedo per tone
    written = {}
    for tone, folder in tones.items():
        src = TB.read_image(_skin_png(folder))
        col = TB.sample(src, uvo)[:, :3].astype(np.float64)
        # grade: the CC0 bronze/tan sources are saturated orange and the runtime tint + subsurface add warmth again,
        # so pull saturation down and cool slightly; keep a little more on light/dark tones
        sat = {"light": 0.86, "medium": 0.72, "tan": 0.78, "dark": 0.9}.get(tone, 0.85) if cid in ("kael", "lyra") else 0.86
        l0 = (col @ np.array((0.3, 0.59, 0.11)))[:, None]
        col = l0 + (col - l0) * sat
        col = col * np.array((0.985, 1.0, 1.025))
        lum = col.mean(1, keepdims=True)
        col = col * (1 - 0.012 * pores[:, None])
        col = col * (1 + np.clip(cheeks + nose_b * 0.8, 0, 1)[:, None] * np.array((0.09, -0.035, -0.05)))
        col = col * (1 + lips[:, None] * np.array((0.1, -0.05, -0.035)))
        col = col * (1 + ears[:, None] * np.array((0.07, -0.025, -0.035)))
        under = blob(FL["eyeL"] + np.array((0.004, -0.004, -0.016)), 0.011) + blob(FL["eyeR"] + np.array((-0.004, -0.004, -0.016)), 0.011)
        col = col * (1 - np.clip(under, 0, 1)[:, None] * np.array((0.07, 0.08, 0.04)))
        if beard > 0:
            col = col * (1 - beard * beard_m[:, None] * np.array((0.2, 0.18, 0.15)))
        col = col * (1 - sc_m[:, None] * np.array((0.55, 0.58, 0.6)))
        col = col * (0.8 + 0.2 * ao_t[:, None])
        ink = np.array((0.06, 0.1, 0.12)) if cid == "kael" else np.array((0.12, 0.05, 0.12))
        col = col * (1 - tcov[:, None] * 0.7) + ink * tcov[:, None] * 0.7 * lum
        img = TB.dilate(_full(T, idx, col), T.cov.reshape(T.size, T.size), 12)
        TB.write_png(img, os.path.join(out_dir, f"Skin_{tone}.png"), "RGB")
        written[tone] = f"Skin_{tone}.png"
    TB.write_png(Hn, os.path.join(out_dir, "Skin_Normal.png"), "RGB")
    TB.write_png(TB.dilate(_full(T, idx, MM), T.cov.reshape(T.size, T.size), 12), os.path.join(out_dir, "Skin_MaskMap.png"), "RGBA")
    if beard > 0:
        TB.write_png(TB.dilate(_full(T, idx, beard_m), T.cov.reshape(T.size, T.size), 12), os.path.join(out_dir, "Skin_Stubble.png"))
    tat = None
    if regs:
        TB.write_png(TB.dilate(_full(T, idx, trgb), T.cov.reshape(T.size, T.size), 6), os.path.join(out_dir, "Skin_Tattoo.png"), "RGB")
        TB.write_png(TB.dilate(_full(T, idx, tcov), T.cov.reshape(T.size, T.size), 6), os.path.join(out_dir, "Skin_TattooMask.png"))
        tat = "Skin_Tattoo.png"
    return written, tat


def _full(T, idx, vals):
    vals = np.asarray(vals, np.float32)
    out = np.zeros((T.size * T.size,) + vals.shape[1:], np.float32)
    out[idx] = vals
    return out.reshape((T.size, T.size) + vals.shape[1:])


def TS_normal(T, idx, h):
    H = TB.blur(TB.dilate(_full(T, idx, h), T.cov.reshape(T.size, T.size), 6), 1)   # pre-filter: no texel-scale aliasing
    return TB.height_to_normal(H, T.mpt.reshape(T.size, T.size), 1.0)
