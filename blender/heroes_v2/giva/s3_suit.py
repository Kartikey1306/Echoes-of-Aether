"""Stage 3: Giva's tech suit (Top + Pants) built from the body's own topology.

  blender -b out/giva_rig.blend --python s3_suit.py [-- --preview]

Top: torso to the waist seam, high neckline, both sleeves to the wrist; the concept's colour-blocked panels are
raised as real bonded overlays (lib/design.py, lib/relief.py). Pants: belt line to inside the boot shafts. Both are one Catmull-Clark level above the body
(more loops at elbows/knees/shoulders), keep every customisation/expression shape, sit >= 3 mm above the skin with
concavities bridged (cleavage, spine groove, gluteal cleft) like stretch fabric. Saves out/giva_suit.blend.
"""
import bpy, bmesh, sys, os, json, math, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
from mathutils import Vector
import gv, garment, deform, design, relief
for m in (gv, garment, deform, design, relief):
    importlib.reload(m)
P = gv.P

Z_BELT = 0.995          # Top/Pants split (hidden by the belt)
Z_PANTS_END = 0.255     # inside the boot shafts


def bone_family(names, W, pred):
    cols = [j for j, n in enumerate(names) if pred(n[len(P):])]
    return W[:, cols].sum(1) if cols else np.zeros(len(W))


def main():
    a = gv.args()
    rig = bpy.data.objects[gv.RIG]
    body = bpy.data.objects["Body"]
    F = garment.Frames(rig)
    X = gv.basis_co(body)
    me = body.data
    names, W = gv.bone_weights(body)
    hand = bone_family(names, W, lambda s: "Hand" in s and "ForeArm" not in s)
    head = bone_family(names, W, lambda s: s in ("Head", "Jaw", "LeftEye", "RightEye") or "Orbicularis" in s)
    arm = bone_family(names, W, lambda s: any(k in s for k in ("Arm", "Hand", "Shoulder")))
    foot = bone_family(names, W, lambda s: "Foot" in s or "Toe" in s)
    polys = me.polygons
    fc = np.array([p.center[:] for p in polys])
    fv = [list(p.vertices) for p in polys]
    fh = np.array([hand[v].mean() for v in fv])
    fhead = np.array([head[v].mean() for v in fv])
    farm = np.array([arm[v].mean() for v in fv])
    ffoot = np.array([foot[v].mean() for v in fv])
    upper = (fc[:, 2] > Z_BELT - 0.03) & (fh < 0.6) & (fhead < 0.5) & (fc[:, 2] < 1.62)
    lower = (fc[:, 2] < Z_BELT + 0.03) & (fc[:, 2] > Z_PANTS_END - 0.03) & (farm < 0.3) & (ffoot < 0.5)
    top = garment.extract(body, upper, "Top")
    pants = garment.extract(body, lower, "Pants")
    # ------------------------------------------------------------ exact cuts
    neck = F.h["Neck"]
    garment.bisect(top, neck + np.array([0, 0, -0.005]), (0, -0.42, 0.91), "below")       # neckline (front lower)
    garment.bisect(top, (0, 0, Z_BELT), (0, 0, 1), "above")
    garment.bisect(pants, (0, 0, Z_BELT), (0, 0, 1), "below")
    garment.bisect(pants, (0, 0, Z_PANTS_END), (0, 0, 1), "above")
    for side, frac in (("Left", 0.93), ("Right", 0.93)):
        fa_h, fa_t = F.h[side + "ForeArm"], F.t[side + "ForeArm"]
        d = (fa_t - fa_h) / np.linalg.norm(fa_t - fa_h)
        c = fa_h + (fa_t - fa_h) * frac
        # cut only the arm: plane through c perpendicular to the forearm, keep the elbow side
        _cut_limb(top, c, d, side)
    gv.log("cut", "Top", len(top.data.vertices), "Pants", len(pants.data.vertices))
    # ------------------------------------------------------------ subdivide + gap
    tris_b = gv.tri_index(me)
    skin = garment.Surface(smoothed_skin(body, X, F), tris_b)
    dissolve_group(top, "nippleTip")
    for o, part in ((top, "top"), (pants, "pants")):
        garment.subdivide(o, 1)
        fit(o, skin, F, part)
        gv.link_armature(o, rig)
        nn, WW = gv.bone_weights(o)
        gv.write_weights(o, nn, gv.limit_normalize(WW, 4, 0.01))
        gv.log(o.name, "verts", len(o.data.vertices), "tris", len(gv.tri_index(o.data)),
               "shapes", len(o.data.shape_keys.key_blocks) - 1 if o.data.shape_keys else 0)
    for o, part in ((top, "top"), (pants, "pants")):
        add_relief(o, part, F)
    collar = build_collar(top, body, F, rig)
    garment.strip_body(body, [top, pants])
    gv.save(os.path.join(gv.OUT, "giva_suit.blend"))


# ----------------------------------------------------------------------------- bonded panels (real geometry)

PANEL_H = {"violet": 0.0019, "sash": 0.0032}


def add_relief(o, part, F):
    """Colour-blocked panels of the master concept as real raised overlays (design.py fields); never within two
    rings of a hem/neckline/cuff (the Top/Pants split at the waist is a construction seam: panels run across it)."""
    for key in ("violet", "sash"):
        X = gv.basis_co(o)
        me = o.data
        off, idx = gv.neighbours(me)
        bnd = np.zeros(len(X))
        for L in garment.boundary_loops(me):
            if abs(X[L, 2].mean() - Z_BELT) < 0.012 and np.ptp(X[L, 2]) < 0.02:
                continue
            bnd[L] = 1
        near = gv.smooth(bnd, off, idx, 3, 0.5) > 0.02
        reg = relief.vertex_regions(o, part, design)
        f = design.fields(X, F, reg)
        relief.raise_panels(o, f[key], PANEL_H[key], exclude=near, name=key)


# ----------------------------------------------------------------------------- collar / cuffs

COLLAR_H = {"back": 0.050, "side": 0.044, "front": 0.036}


def morph_bind(o, body, Xo):
    """Customisation-morph shapes for a new garment part via a surface binding to the body."""
    Xb = gv.basis_co(body)
    tb = gv.tri_index(body.data)
    bind = gv.Binding(Xb, tb, Xo, 0.3)
    for n, co in gv.shape_dict(body).items():
        if not n.startswith("m_"):
            continue
        d = bind.transfer(co - Xb)
        if np.abs(d).max() > 1e-5:
            gv.add_shape(o, n, Xo + d)
    return bind


def weights_bind(o, src, Xo, extra=None):
    """Weights interpolated from src's rest surface; extra: [(mask, {bone: w})] blends towards fixed weights."""
    Xs = gv.basis_co(src)
    ts = gv.tri_index(src.data)
    names, W = gv.bone_weights(src)
    bind = gv.Binding(Xs, ts, Xo, 0.3)
    Wo = bind.transfer(W)
    if extra:
        for mask, fixed in extra:
            Wf = np.zeros_like(Wo)
            for b, w in fixed.items():
                if P + b not in names:
                    names.append(P + b)
                    Wo = np.concatenate([Wo, np.zeros((len(Wo), 1))], 1)
                    Wf = np.concatenate([Wf, np.zeros((len(Wf), 1))], 1)
                Wf[:, names.index(P + b)] = w
            Wo = Wo * (1 - mask[:, None]) + Wf * mask[:, None]
    gv.write_weights(o, names, gv.limit_normalize(Wo, 4, 0.01))


def build_collar(top, body, F, rig):
    """High tactical (mandarin) collar standing on the neckline, flaring slightly, rounded top edge; joined into
    Top as its own UV island later. Weights blend from the neckline to Neck/Spine2 at the top."""
    Xt = gv.basis_co(top)
    loops = garment.boundary_loops(top.data)
    neck = F.h["Neck"]
    up = gv.nrm(F.t["Neck"] - F.h["Neck"]) * 0.55 + np.array((0, 0, 1.0)) * 0.45
    up = gv.nrm(up)
    # the neckline loop is the one nearest the neck
    li = int(np.argmin([np.linalg.norm(Xt[L].mean(0) - neck) for L in loops]))
    L = garment.order_loop_by_angle(Xt, loops[li], neck, up)
    B = Xt[L]
    # resample the loop uniformly (smooth collar independent of the body edge spacing)
    seg = np.linalg.norm(np.roll(B, -1, 0) - B, axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    tot = s[-1]
    n = 72
    u = np.linspace(0, tot, n, endpoint=False)
    Bc = np.concatenate([B, B[:1]])
    base = np.stack([np.interp(u, s, Bc[:, k]) for k in range(3)], 1)
    # smooth the base curve a little
    for _ in range(3):
        base = 0.5 * base + 0.25 * (np.roll(base, 1, 0) + np.roll(base, -1, 0))
    c = base.mean(0)
    frames, heights = [], []
    for p in base:
        O = p - c
        O = O - up * (O @ up)
        O /= np.linalg.norm(O)
        ang = math.atan2(O[0], -O[1])           # 0 front, +pi/2 left
        fr = abs(math.cos(ang))
        h = COLLAR_H["front"] * max(0, math.cos(ang)) ** 1.5 + COLLAR_H["back"] * max(0, -math.cos(ang)) ** 1.5 \
            + COLLAR_H["side"] * (1 - fr ** 1.5)
        frames.append((O, up))
        heights.append(h)
    # profile: inner wall up, flare, rounded lip, outer wall down and tucked under the suit surface
    prof_unit = [(-0.0015, -0.006), (0.0, 0.0), (0.0015, 0.35), (0.0045, 0.75), (0.0062, 0.93), (0.0085, 1.0),
                 (0.0112, 0.95), (0.0128, 0.8), (0.0122, 0.45), (0.0098, 0.12), (0.0072, -0.02), (0.0045, -0.09)]
    V, Fq = [], []
    m = len(prof_unit)
    for i, p in enumerate(base):
        O, U = frames[i]
        for j_, (po, pu) in enumerate(prof_unit):
            # inner wall starts 6 mm below the neckline; the outer wall tucks just under the suit surface
            hh = pu * heights[i] if (pu > 0 or j_ > 0) else pu
            lean = -0.018 * max(0.0, pu) ** 1.2          # mock neck: the top closes in on the neck
            V.append(p + O * (po + lean) + U * hh)
    for i in range(n):
        i2 = (i + 1) % n
        for j in range(m - 1):
            Fq.append((i * m + j, i2 * m + j, i2 * m + j + 1, i * m + j + 1))
    V = np.array(V)
    o = gv.mesh_obj("Collar", V, Fq)
    for p_ in o.data.polygons:
        p_.use_smooth = True
    # attributes for texturing: around (0..1), height fraction, inner/outer
    hf = np.array([max(0.0, pu) for _ in range(n) for po, pu in prof_unit])
    side = np.array([float(j >= 6) for _ in range(n) for j in range(m)])
    mask = np.clip(hf, 0, 1) ** 0.8
    weights_bind(o, top, V, [(mask * 0.7, {"Neck": 0.6, "Spine2": 0.4})])
    morph_bind(o, body, V)
    gv.link_armature(o, rig)
    gv.log("collar", len(V), "verts")
    return o


def build_cuff(top, body, F, rig, side):
    """Rolled cuff on the 3/4 sleeve: the boundary folds over into a 4 mm thick rim."""
    Xt = gv.basis_co(top)
    loops = garment.boundary_loops(top.data)
    fa_h, fa_t = F.h[side + "ForeArm"], F.t[side + "ForeArm"]
    ax = gv.nrm(fa_t - fa_h)
    target = fa_h + (fa_t - fa_h) * 0.52
    li = int(np.argmin([np.linalg.norm(Xt[L].mean(0) - target) for L in loops]))
    L = garment.order_loop_by_angle(Xt, loops[li], target, ax)
    B = Xt[L]
    c = B.mean(0)
    prof = [(0.0, 0.0), (0.0022, 0.0006), (0.0042, 0.0), (0.0048, -0.004), (0.0040, -0.009), (0.0018, -0.011)]
    V, Fq = [], []
    for p in B:
        O = gv.nrm((p - c) - ax * ((p - c) @ ax))
        for po, pu in prof:
            V.append(p + O * po + ax * pu)
    n, m = len(B), len(prof)
    for i in range(n):
        i2 = (i + 1) % n
        for j in range(m - 1):
            Fq.append((i * m + j, i2 * m + j, i2 * m + j + 1, i * m + j + 1))
    V = np.array(V)
    o = gv.mesh_obj("Cuff" + side, V, Fq)
    for p_ in o.data.polygons:
        p_.use_smooth = True
    weights_bind(o, top, V)
    morph_bind(o, body, V)
    gv.link_armature(o, rig)
    return o


def _cut_limb(o, c, d, side):
    """Remove the part of the forearm beyond the plane (c, d) but only on that arm's side of the body."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    sx = 1 if side == "Left" else -1
    geom = [f for f in bm.faces if sx * f.calc_center_median().x > 0.25]
    gverts = list({v for f in geom for v in f.verts})
    gedges = list({e for f in geom for e in f.edges})
    res = bmesh.ops.bisect_plane(bm, geom=gverts + gedges + geom, dist=1e-6, plane_co=Vector(c), plane_no=Vector(d),
                                 clear_outer=False, clear_inner=False)
    kill = [f for f in bm.faces if sx * f.calc_center_median().x > 0.25 and (Vector(f.calc_center_median()) - Vector(c)).dot(Vector(d)) > 0]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()


def dissolve_group(o, name):
    """Dissolve the MPFB nipple-tip micro faces (tiny triangles that shade as a point through any smoothing)."""
    g = o.vertex_groups.get(name)
    if g is None:
        return
    bm = bmesh.new()
    bm.from_mesh(o.data)
    dl = bm.verts.layers.deform.active
    vs = [v for v in bm.verts if dl and g.index in v[dl] and v[dl][g.index] > 0.3]
    bmesh.ops.dissolve_verts(bm, verts=vs, use_face_split=False, use_boundary_tear=False)
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    gv.log("dissolved", len(vs), name, "verts")


def bust_mask(o, X, F, rings):
    """Geometric mask around each nipple centre (radius grows with `rings`: 0.6 cm per ring + 1.5 cm)."""
    tip = group_mask(o, "nippleTip") > 0.01
    if tip.sum() == 0:
        tip = group_mask(o, "nipple") > 0.01
    m = np.zeros(len(X))
    for sgn in (1, -1):
        sel = tip & (np.sign(X[:, 0]) == sgn)
        if sel.sum() == 0:
            continue
        c = X[sel].mean(0)
        d = np.linalg.norm(X - c, axis=1)
        r = 0.015 + 0.006 * rings
        m = np.maximum(m, 1 - gv.ss(r * 0.25, r, d))
    return m


def anatomy_mask(o, X, F):
    """Areas a suit never shows: nipples, the vulva/crotch front, the navel pit."""
    me = o.data
    off, idx = gv.neighbours(me)
    m = np.maximum(group_mask(o, "nipple"), group_mask(o, "nippleTip"))
    z, phi = F.torso(X)
    crotch = (np.abs(X[:, 0]) < 0.055) & (z > 0.80) & (z < 0.95) & (X[:, 1] < 0.02)
    navel = (np.abs(X[:, 0]) < 0.03) & (np.abs(z - 1.08) < 0.03) & (X[:, 1] < -0.08)
    m = np.maximum(m, crotch.astype(float))
    m = np.maximum(m, navel.astype(float))
    return np.clip(gv.smooth((m > 0.01).astype(float), off, idx, 6, 0.5) * 3, 0, 1)


def smoothed_skin(body, X, F):
    """Body rest surface with the anatomy smoothed away (reference surface for the suit's skin gap)."""
    off, idx = gv.neighbours(body.data)
    Y = gv.smooth(X, off, idx, 40, 0.5, mask=anatomy_mask(body, X, F))
    return gv.taubin(Y, off, idx, 25, mask=bust_mask(body, X, F, 4))


def group_mask(o, name):
    g = o.vertex_groups.get(name)
    m = np.zeros(len(o.data.vertices))
    if g is None:
        return m
    for v in o.data.vertices:
        for e in v.groups:
            if e.group == g.index:
                m[v.index] = e.weight
    return m


def fit(o, skin, F, part):
    """Fabric fit for the basis (gap, bridging, tension smoothing); the same offsets go to every shape key."""
    me = o.data
    X0 = gv.basis_co(o)
    tris = gv.tri_index(me)
    off, idx = gv.neighbours(me)
    z, phi = F.torso(X0)
    gap = np.full(len(X0), 0.003)
    # boundary rings stay put (cuffs / neckline / cuts are handled by rims)
    bnd = np.zeros(len(X0))
    for L in garment.boundary_loops(me):
        bnd[L] = 1
    keep = gv.smooth(bnd, off, idx, 2, 0.5) > 0.05
    # strong local smoothing: nipples, genitals (no anatomy showing through the suit)
    loc = anatomy_mask(o, X0, F)
    bmask = np.zeros(len(X0))
    if part == "top":
        tor = (np.abs(X0[:, 0]) < 0.17) & (z > 1.08) & (z < 1.45)
        bmask[tor] = 1.0
    else:
        b = (np.abs(X0[:, 0]) < 0.07) & (z > 0.72)
        bmask[b] = 1.0
    bmask = gv.smooth(bmask, off, idx, 4, 0.5)
    X = X0.copy()
    # 1) local anatomy smoothing (both directions)
    X = gv.smooth(X, off, idx, 50, 0.5, mask=loc * (1 - keep))
    if part == "top":
        X = gv.taubin(X, off, idx, 30, mask=bust_mask(o, X0, F, 8) * (1 - keep))
    # 2) outward bridging of concavities (stretch fabric spans cleavage, sternum, spine groove, cleft)
    X = garment.push_out(X, tris, off, idx, skin, gap, bridge_iters=60, bridge_mask=bmask * (1 - keep))
    # 3) overall fabric tension: mild smoothing, then the skin gap again
    X = gv.smooth(X, off, idx, 4, 0.4, mask=(1 - keep).astype(float))
    X = garment.push_out(X, tris, off, idx, skin, gap)
    if part == "top":
        # final: no nipple point survives (body is stripped underneath, so no gap constraint here)
        bm3 = bust_mask(o, X0, F, 3) * (1 - keep)
        X = gv.smooth(X, off, idx, 25, 0.5, mask=bm3)
        # the MPFB nipple is a dense pole of concentric rings: spread them so shading has no pinch point
        X = gv.relax_tangent(X, tris, off, idx, 40, 0.5, mask=bust_mask(o, X0, F, 6) * (1 - keep))
    D = X - X0
    shapes = gv.shape_dict(o)
    gv.set_co(o, X)
    if me.shape_keys:
        me.shape_keys.key_blocks[0].data.foreach_set("co", X.astype(np.float32).ravel())
        for n, co in shapes.items():
            if np.abs(co - X0).max() < 1e-5:
                o.shape_key_remove(me.shape_keys.key_blocks[n])
                continue
            me.shape_keys.key_blocks[n].data.foreach_set("co", (co + D).astype(np.float32).ravel())
    me.update()
    gv.log(o.name, "fit: max offset %.1f mm" % (np.linalg.norm(D, axis=1).max() * 1000))


main()
