"""Lofted subdivision car shells (lower body + greenhouse), panel grooves, wheel arches, light recesses.

Coordinates: build space (front +Y, right +X, up Z).  `s` = forward coordinate (= y).
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import vkit as K

# lower body ring: 9 half points p0..p8 -> 16-vert ring [p0, p1R..p7R, p8, p7L..p1L]
LOWER_N = 16
# greenhouse ring: 7 half points g0..g6 -> 12-vert ring [g0, g1R..g5R, g6, g5L..g1L]
GH_N = 12


def mirror_ring(half):
    """half: list of (x, z) from bottom centre (x=0) to top centre (x=0)."""
    right = half
    left = [(-x, z) for (x, z) in reversed(half[1:-1])]
    return right + left


def lower_half(P, s):
    w, rin, zb, zr, zc = P("w", s), P("rin", s), P("zb", s), P("zr", s), P("zc", s)
    zs, tin, zd, crown, dw = P("zs", s), P("tin", s), P("zd", s), P("crown", s), P("dw", s)
    xs = w - tin
    z6 = zs - 0.01 + (zd - zs) * P("fender", s)
    return [(0.0, zb), (0.55 * (w - rin), zb), (w - rin - 0.035, zb + 0.012), (w - rin, zr), (w, zc), (xs, zs),
            (xs * dw, z6), (xs * dw * 0.5, zd + crown * 0.75), (0.0, zd + crown)]


def gh_half(G, s):
    xb, zbelt, xw, zw = G("xb", s), G("zbelt", s), G("xw", s), G("zw", s)
    xr, zre, zroof, zbot = G("xr", s), G("zre", s), G("zroof", s), G("zbot", s)
    # keep the ring ordered where the roof dives into the body at the cabin ends (no fold-overs)
    zw = max(zw, zbelt + 0.006)
    zre = max(zre, zw + 0.006)
    zroof = max(zroof, zre + 0.004)
    xw = min(xw, xb - 0.004)
    xr = min(xr, xw - 0.004)
    return [(0.0, zbot), (xb * 0.85, zbot), (xb, zbelt), (xw, zw), (xr, zre), (xr * 0.5, zroof - 0.006), (0.0, zroof)]


def ring3(half_pts, s):
    return [Vector((x, s, z)) for (x, z) in mirror_ring(half_pts)]


def crease_material_boundaries(p, value=1.0):
    for e in p.bm.edges:
        if len(e.link_faces) == 2 and e.link_faces[0].material_index != e.link_faces[1].material_index:
            e[p.crease] = value


def crease_rows(p, vrows, js, value):
    """Crease the longitudinal edges along ring index j (between consecutive stations)."""
    for j in js:
        for i in range(len(vrows) - 1):
            e = p.bm.edges.get((vrows[i][j], vrows[i + 1][j]))
            if e:
                e[p.crease] = max(e[p.crease], value)


def crease_ring(p, ring, value, js=None):
    n = len(ring)
    for j in range(n):
        if js is not None and j not in js:
            continue
        e = p.bm.edges.get((ring[j], ring[(j + 1) % n]))
        if e:
            e[p.crease] = max(e[p.crease], value)


# ================================================================================================ lower body
def build_lower(spec, lod):
    P = spec["lower"]
    st = spec["stations"]
    p = K.Part("lower")
    rings = [ring3(lower_half(P, s), s) for s in st]
    paint = spec["paint"]
    sill = spec.get("sill_mat", "veh_carbon")
    under = "veh_plastic"
    def mf(i, j):
        jm = j if j <= 7 else 15 - j  # segment j (verts j..j+1); mirror: seg 8 <-> 7, 15 <-> 0
        if jm in (0, 1):
            return under
        if jm == 2:
            return sill
        fn = spec.get("lower_mat_fn")
        if fn:
            m = fn(st[i], st[i + 1], jm)
            if m:
                return m
        return paint
    vrows, fs, _ = K.loft(p, rings, mf, cap0=None, cap1=None)
    # caps: 4 x 4 Coons patches, bottom edge centred on p0
    front_bulge = spec.get("nose_bulge", 0.05)
    rear_bulge = spec.get("tail_bulge", 0.03)
    capf = K.coons_cap(p, vrows[-1], 4, 4, 14, front_bulge, spec.get("fascia_mat", paint), bulge_dir=Vector((0, 1, 0)))
    capr = K.coons_cap(p, vrows[0], 4, 4, 14, rear_bulge, spec.get("tail_mat", paint), bulge_dir=Vector((0, -1, 0)))
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    crease_material_boundaries(p, 1.0)
    for j, v in spec.get("lower_creases", {3: 1.0, 4: 0.55, 5: 0.85}).items():
        crease_rows(p, vrows, [j, 16 - j], v)
    crease_ring(p, vrows[-1], spec.get("nose_crease", 0.6))
    crease_ring(p, vrows[0], spec.get("tail_crease", 0.8))
    ob = p.to_object("lower")
    K.subsurf(ob, spec.get("subd", 2) - (1 if lod >= 1 else 0))
    return ob


# ================================================================================================ greenhouse
def build_greenhouse(spec, lod):
    G = spec["gh"]
    st = spec["gh_stations"]
    z = spec["gh_zones"]  # dict: ws=(s_cowl..s_ws_top), side=(s0,s1), roof_mat, rear_glass=True, bpillar=(s0,s1) or None
    p = K.Part("greenhouse")
    rings = [ring3(gh_half(G, s), s) for s in st]
    paint = spec["paint"]

    def mf(i, j):
        s0, s1 = st[i], st[i + 1]
        sm = 0.5 * (s0 + s1)
        jm = j if j <= 5 else 11 - j
        if jm in (0, 1):
            return paint
        if jm == 2:  # side glass band
            a, b = z["side"]
            if a <= sm <= b:
                bp = z.get("bpillar")
                if bp and bp[0] <= sm <= bp[1]:
                    return z.get("bpillar_mat", "veh_trim")
                return "veh_glass"
            return z.get("cpillar_mat", paint)
        if jm == 3:
            return z.get("rail_mat", paint)
        # roof centre bands
        if sm >= z["ws_top"]:
            return "veh_glass"
        if sm <= z["rear_top"]:
            return "veh_glass" if z.get("rear_glass", True) else z.get("roof_mat", paint)
        return z.get("roof_mat", paint)
    vrows, fs, _ = K.loft(p, rings, mf)
    K.coons_cap(p, vrows[-1], 2, 4, 11, 0.0, paint, bulge_dir=Vector((0, 1, 0)))
    K.coons_cap(p, vrows[0], 2, 4, 11, 0.0, paint, bulge_dir=Vector((0, -1, 0)))
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    crease_material_boundaries(p, 1.0)
    crease_rows(p, vrows, [3, 9], spec.get("gh_crease_glass", 1.0))
    crease_rows(p, vrows, [4, 8], spec.get("gh_crease_rail", 0.7))
    ob = p.to_object("greenhouse")
    K.subsurf(ob, spec.get("gh_subd", 2) - (1 if lod >= 1 else 0))
    if lod == 0:
        K.inset_region_mat(ob, "veh_glass", 0.014, 0.007, frame_mat="veh_trim")
    return ob


# ================================================================================================ wheel arches
def arch_cutters(spec, lod):
    outs = []
    for (s, side_x) in spec["wheel_pos"]:
        R = spec["arch_r"]
        zc = spec["wheel_r"]
        p = K.Part("arch")
        depth = spec.get("arch_depth", 0.62)
        xin = abs(side_x) - spec["wheel_w"] / 2 - 0.08
        n = K.seg(48, 12)
        vs = K.cyl(p, R, 1.4, n=n, axis="X", m="veh_plastic", at=(0, 0, 0))
        sgn = 1 if side_x > 0 else -1
        p.transform(Matrix.Translation((sgn * (xin + 0.7), s, zc)), vs)
        # extend the cut downwards so the opening reaches the sill (box below centre)
        vs = K.box(p, (1.4, 2 * R, zc + 0.1), m="veh_plastic", at=(sgn * (xin + 0.7), s, (zc - 0.1) / 2 - 0.02))
        outs.append(p.to_object("arch_cut"))
    return outs


def arch_lips(spec, surf, mat="veh_carbon", lod=0):
    """Thin flare trims following the arch edge on the body surface."""
    p = K.Part("lips")
    if lod >= 2:
        return p
    R = spec["arch_r"] + 0.012
    zc = spec["wheel_r"]
    for (s, side_x) in spec["wheel_pos"]:
        sgn = 1 if side_x > 0 else -1
        path = []
        a0, a1 = spec.get("lip_angles", (-8, 188))
        n = K.seg(22, 8)
        for k in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * k / n)
            y, z = s + R * math.cos(a), zc + R * math.sin(a)
            loc, nrm = surf.side_x(y, z, sgn)
            if loc is None:
                continue
            path.append(Vector((loc.x + sgn * 0.004, y, z)))
        if len(path) < 3:
            continue
        prof = [(-0.006, -0.008), (0.022, -0.008), (0.025, 0.004), (-0.006, 0.006)]
        # frames: side = radial direction approx; use up = +-X so the profile lies in the arch plane
        rings, fs = K.sweep(p, path, [(a, b) for (a, b) in prof], m=mat, up=Vector((sgn, 0, 0)))
    return p


# ================================================================================================ light recess
def surface_curve(surf, xs, z, sign=1, inset=0.0, axis="y"):
    """Points on the front (sign=+1) / rear (-1) surface at height z for each x; pushed inward by inset."""
    pts = []
    for x in xs:
        loc, n = surf.front_y(x, z, sign)
        if loc is None:
            continue
        pts.append(Vector((x, loc.y - sign * inset, z)))
    return pts


def slot_cutter(path, h, depth_in, out=0.08, m="veh_trim", sign=1, round_r=0.008):
    """Cutter swept along a surface curve: rounded rect h tall, from `out` outside to depth_in inside."""
    p = K.Part("slot")
    # profile in (side, normal) where frames from path tangent (x) and up z -> side = t x up ~ -y*sign
    prof = K.rrect(out + depth_in, h, round_r, n=2)
    prof = [(a + (out - depth_in) / 2 * 0 , b) for (a, b) in prof]
    rings = []
    vrows = []
    for i, c in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        nrm = t.cross(Vector((0, 0, 1))).normalized()
        if nrm.y * sign < 0:
            nrm = -nrm
        row = []
        for (a, b) in prof:
            off = a + (out - depth_in) / 2
            row.append(p.vert(c + nrm * off + Vector((0, 0, b))))
        vrows.append(row)
    K.grid_faces(p, vrows, lambda i, j: m, closed_u=True)
    p.face(list(reversed(vrows[0])), m)
    p.face(vrows[-1], m)
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    return p.to_object("slot_cut")


def light_strip(p, path, h, back, m, sign=1, round_r=0.006, thick=0.02):
    """Emissive strip inside a recess, set `back` metres behind the surface path."""
    prof = K.rrect(thick, h, round_r, n=2)
    vrows = []
    for i, c in enumerate(path):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        nrm = t.cross(Vector((0, 0, 1))).normalized()
        if nrm.y * sign < 0:
            nrm = -nrm
        vrows.append([p.vert(c + nrm * (a - back - thick / 2) + Vector((0, 0, b))) for (a, b) in prof])
    fs = K.grid_faces(p, vrows, lambda i, j: m, closed_u=True)
    p.face(list(reversed(vrows[0])), m)
    p.face(vrows[-1], m)
    return fs


def side_curve(surf, ys, z, sign=1, inset=0.0):
    pts = []
    for y in ys:
        loc, n = surf.side_x(y, z, sign)
        if loc is None:
            continue
        pts.append(Vector((loc.x - sign * inset, y, z)))
    return pts


def side_slot_cutter(path, h, depth_in, out=0.08, m="veh_plastic", sign=1, r=0.01):
    p = K.Part("sslot")
    prof = K.rrect(out + depth_in, h, r, n=2)
    vrows = []
    for i, c in enumerate(path):
        nrm = Vector((sign, 0, 0))
        vrows.append([p.vert(c + nrm * (a + (out - depth_in) / 2) + Vector((0, 0, b))) for (a, b) in prof])
    K.grid_faces(p, vrows, lambda i, j: m, closed_u=True)
    p.face(list(reversed(vrows[0])), m)
    p.face(vrows[-1], m)
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    return p.to_object("sslot_cut")


# ================================================================================================ interior
def interior(spec, lod):
    """Cabin tub (inward-facing), headliner, dash, bucket seats, centre console, steering yoke."""
    c = spec["cabin"]  # dict: s0 (rear), s1 (front), hw (half width), floor, belt, roof, seat_rows
    p = K.Part("interior")
    m = "veh_interior"
    s0, s1, hw, fl, belt = c["s0"], c["s1"], c["hw"], c["floor"], c["belt"]
    # tub: open box, normals inward
    vs = K.box(p, (2 * hw, s1 - s0, belt - fl), at=(0, (s0 + s1) / 2, (fl + belt) / 2), m=m)
    fs = K.faces_of(vs)
    top = [f for f in fs if f.normal.z > 0.9]
    bmesh.ops.delete(p.bm, geom=top, context="FACES_ONLY")
    fs = [f for f in K.faces_of([v for v in vs if v.is_valid]) if f.is_valid]
    bmesh.ops.reverse_faces(p.bm, faces=fs)
    # headliner
    hl = c.get("headliner")
    if hl:
        hs0, hs1, hz, hhw = hl
        v = [p.vert((-hhw, hs0, hz)), p.vert((hhw, hs0, hz)), p.vert((hhw, hs1, hz)), p.vert((-hhw, hs1, hz))]
        p.face(list(reversed(v)), m)  # facing down into the cabin
    if lod >= 2:
        return p
    # dash
    ds = c.get("dash_s", s1 - 0.12)
    dz = c.get("dash_z", belt - 0.06)
    K.box(p, (2 * hw - 0.04, 0.32, 0.16), at=(0, ds, dz), m="veh_trim", bevel=0.02, bseg=2)
    if lod == 0 and c.get("dash_glow", True):
        K.box(p, (2 * hw - 0.12, 0.012, 0.012), at=(0, ds - 0.165, dz + 0.04), m="veh_neon")
        # instrument screen
        K.box(p, (0.36, 0.01, 0.1), at=(-c.get("driver_x", 0.36), ds - 0.16, dz + 0.1), m="veh_trim", M=Matrix.Rotation(math.radians(-15), 4, "X"))
    # seats (reclined buckets): seat_h = headrest height above floor
    sh = c.get("seat_h", 0.70)
    rec = c.get("recline", 22)
    for ri, row in enumerate(c.get("seat_rows", [(s0 + 0.45, (-0.36, 0.36))])):
        sy, xs_ = row
        for sx in xs_:
            K.box(p, (0.5, 0.50, 0.12), at=(sx, sy, fl + 0.10), m=m, bevel=0.03, bseg=2)
            back = K.box(p, (0.5, 0.11, sh * 0.78), m=m, bevel=0.035, bseg=2)
            p.transform(Matrix.Translation((sx, sy - 0.27, fl + 0.14 + sh * 0.36)) @ Matrix.Rotation(math.radians(-rec), 4, "X"), back)
            if lod == 0 and ri == 0:
                for bx in (-1, 1):  # bolsters (front row only)
                    bol = K.box(p, (0.07, 0.14, sh * 0.6), m=m, bevel=0.025, bseg=2)
                    p.transform(Matrix.Translation((sx + bx * 0.23, sy - 0.24, fl + 0.14 + sh * 0.33)) @ Matrix.Rotation(math.radians(-rec), 4, "X"), bol)
                hr = K.box(p, (0.26, 0.1, 0.15), m=m, bevel=0.03, bseg=2)
                p.transform(Matrix.Translation((sx, sy - 0.27 - math.sin(math.radians(rec)) * sh * 0.62, fl + 0.14 + sh * 0.88)) @ Matrix.Rotation(math.radians(-rec), 4, "X"), hr)
    # console
    K.box(p, (0.2, (s1 - s0) * 0.55, 0.22), at=(0, s0 + (s1 - s0) * 0.55, fl + 0.13), m="veh_trim", bevel=0.02)
    # yoke
    dx = c.get("driver_x", -0.36)
    yz = c.get("yoke_z", dz + 0.02)
    ys_ = c.get("yoke_s", ds - 0.28)
    col = K.cyl(p, 0.025, 0.25, n=8, axis="Y", m="veh_metal", at=(dx, ys_ + 0.13, yz - 0.02))
    path = []
    for k in range(9):
        a = math.radians(200 + 140 * k / 8)
        path.append(Vector((dx + 0.17 * math.cos(a), ys_, yz + 0.11 + 0.12 * math.sin(a))))
    K.sweep(p, path, K.circle(0.017, 6 if lod == 0 else 4), m="veh_trim", up=Vector((0, 1, 0)))
    K.box(p, (0.34, 0.03, 0.035), at=(dx, ys_, yz + 0.0), m="veh_trim", bevel=0.01)
    K.box(p, (0.12, 0.04, 0.08), at=(dx, ys_ + 0.01, yz + 0.01), m="veh_metal", bevel=0.01)
    return p
