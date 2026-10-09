"""Ground cars: CyberCar_Coupe, CyberCar_Sedan, CyberCar_Taxi, CyberCar_Sedan_Wrecked.

Each spec drives carbody (lofted subdivision shell) + shared detail builders. build_car(spec, lod) returns
{'body': obj, 'wheels': {name: (obj, centre)}, 'lights': {...}, 'colliders': [...]} in build space.
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import carbody as CB
import vkit as K
import vtex
import wheels as WH
from vkit import Profile


# ================================================================================================ context
class Ctx:
    def __init__(self, spec, lod):
        self.spec = spec
        self.lod = lod
        self.parts = []
        self.cutters = []
        self.lights = {}
        self.extra = {}

    def part(self, name):
        p = K.Part(name)
        self.parts.append(p)
        return p


# ================================================================================================ shared details
def front_bar(ctx, z, half, h, mat="veh_headlight", depth=0.05, back=0.012, sign=1, key="head", n=24, recess_mat="veh_trim"):
    """Full-width LED bar recessed into the front (sign=+1) or rear (-1) face."""
    xs = [-half + 2 * half * k / n for k in range(n + 1)]
    path = CB.surface_curve(ctx.surf, xs, z, sign)
    if len(path) < 3:
        return
    cut = CB.slot_cutter(path, h, depth, out=0.1, m=recess_mat, sign=sign, round_r=min(h * 0.45, 0.012))
    ctx.cutters.append(cut)
    p = ctx.part(f"bar_{key}")
    CB.light_strip(p, path, h * 0.72, back, mat, sign=sign, thick=0.02, round_r=h * 0.3)
    mid = path[len(path) // 2]
    ctx.lights.setdefault(key, []).append([0.0, mid.y, z])


def side_bar(ctx, y0, y1, z, h, mat, sign_x, n=10, depth=0.04, back=0.01, recess_mat="veh_trim"):
    ys = [y0 + (y1 - y0) * k / n for k in range(n + 1)]
    path = CB.side_curve(ctx.surf, ys, z, sign_x)
    if len(path) < 3:
        return
    p = K.Part("sb")
    prof = K.rrect(0.1 + depth, h, min(h * 0.45, 0.01), n=2)
    vrows = [[p.vert(c + Vector((sign_x, 0, 0)) * (a + (0.1 - depth) / 2) + Vector((0, 0, b))) for (a, b) in prof] for c in path]
    K.grid_faces(p, vrows, lambda i, j: recess_mat, closed_u=True)
    p.face(list(reversed(vrows[0])), recess_mat)
    p.face(vrows[-1], recess_mat)
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    ctx.cutters.append(p.to_object("sbcut"))
    q = ctx.part("sbar")
    prof2 = K.rrect(0.02, h * 0.7, h * 0.3, n=2)
    vrows = [[q.vert(c + Vector((sign_x, 0, 0)) * (a - back - 0.01) + Vector((0, 0, b))) for (a, b) in prof2] for c in path]
    K.grid_faces(q, vrows, lambda i, j: mat, closed_u=True)
    q.face(list(reversed(vrows[0])), mat)
    q.face(vrows[-1], mat)


def splitter(ctx, z, half, s_back, reach=0.06, thick=0.022, mat="veh_carbon", endplates=True):
    xs = [-half + 2 * half * k / 16 for k in range(17)]
    pts = CB.surface_curve(ctx.surf, xs, z + thick + 0.03, 1)
    if len(pts) < 3:
        return
    p = ctx.part("splitter")
    poly = [(c.x, c.y + reach) for c in pts] + [(half * 0.95, s_back), (-half * 0.95, s_back)]
    # polygon must be CCW in XY: front edge goes -x -> +x at high y, so reverse for CCW
    poly = list(reversed(poly))
    K.extrude_poly(p, poly, thick, M=Matrix.Translation((0, 0, z)), m=mat)
    if endplates and ctx.lod < 2:
        for sx in (-1, 1):
            c = pts[0] if sx < 0 else pts[-1]
            K.box(p, (0.012, 0.22, 0.09), at=(c.x + sx * 0.0, c.y - 0.04, z + 0.06), m=mat, bevel=0.004)


def diffuser(ctx, s0, s1, z_lo, z_hi, half, fins=5, mat="veh_carbon"):
    p = ctx.part("diffuser")
    # floor ramp
    poly = [(s0, z_lo), (s1, z_lo), (s1, z_hi), (s0 + 0.08, z_lo + 0.01)]
    for k in range(fins):
        x = -half + 2 * half * k / (fins - 1)
        fin = [(s1 - 0.02, z_lo - 0.005), (s0 + 0.15, z_lo - 0.005), (s1 - 0.02, z_hi + 0.01)]
        # fin is a thin plate in the YZ plane at x
        q = [(y, zz) for (y, zz) in fin]
        vs = K.extrude_poly(p, [(a, b) for (a, b) in q], 0.012, M=Matrix.Translation((x - 0.006, 0, 0)) @ Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))), m=mat)


def underglow(ctx, s0, s1, x, z, mat="veh_underglow", w=0.022, front=None):
    p = ctx.part("underglow")
    for sx in (-1, 1):
        K.box(p, (w, s1 - s0, 0.012), at=(sx * x, (s0 + s1) / 2, z), m=mat)
    if front:
        fs, fx = front
        K.box(p, (2 * fx, w, 0.012), at=(0, fs, z), m=mat)


def badge(ctx, centre, normal, w, h, cell, up=Vector((0, 0, 1)), raise_=0.004, thick=0.006):
    """Raised plate with an atlas glyph cell, aligned to a surface normal."""
    p = ctx.part("badge")
    nrm = Vector(normal).normalized()
    side = up.cross(nrm)
    if side.length < 1e-4:
        side = Vector((1, 0, 0))
    side.normalize()
    upv = nrm.cross(side).normalized()
    c = Vector(centre) + nrm * raise_
    corners = [c + side * (-w / 2) + upv * (-h / 2), c + side * (w / 2) + upv * (-h / 2), c + side * (w / 2) + upv * (h / 2), c + side * (-w / 2) + upv * (h / 2)]
    top = [p.vert(v) for v in corners]
    bot = [p.vert(v - nrm * (thick + raise_)) for v in corners]
    f = p.face(top, "veh_decal")
    for i in range(4):
        p.face([bot[i], bot[(i + 1) % 4], top[(i + 1) % 4], top[i]], "veh_chrome")
    if f:
        u0, v0, u1, v1 = vtex.atlas_rect(cell)
        for l, (uu, vv) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            l[p.uv].uv = (u0 + uu * (u1 - u0), v0 + vv * (v1 - v0))
        # make sure the glyph face points along the normal
        f.normal_update()
        if f.normal.dot(nrm) < 0:
            # flip winding but keep UV orientation mirrored correctly
            bmesh.ops.reverse_faces(p.bm, faces=[f])
            for l in f.loops:
                uv = l[p.uv].uv
                l[p.uv].uv = (u0 + u1 - uv.x, uv.y)


def badge_on(ctx, origin, direction, w, h, cell, up=Vector((0, 0, 1))):
    loc, n = ctx.surf.hit(origin, direction)
    if loc is None:
        return
    badge(ctx, loc, n, w, h, cell, up=up)


def mirror_cams(ctx, s, z, reach=0.10, accent="veh_neon"):
    p = ctx.part("mirrors")
    for sx in (-1, 1):
        loc, n = ctx.surf.side_x(s, z, sx)
        if loc is None:
            continue
        base = Vector((loc.x - sx * 0.01, s, z))
        # stalk
        K.box(p, (reach + 0.02, 0.03, 0.012), at=(base.x + sx * reach / 2, s - 0.01, z + 0.03), m="veh_trim", bevel=0.004,
              M=Matrix.Rotation(math.radians(sx * -8), 4, "Y"))
        # aero pod (lathe along Y, pointing forward)
        prof = [(0.0, 0.10), (0.018, 0.085), (0.032, 0.04), (0.036, -0.01), (0.034, -0.05), (0.0, -0.05)]
        rings, fs = K.lathe(p, prof, n=K.seg(14, 6), axis="Y", m=ctx.spec["paint"], at=(base.x + sx * (reach + 0.02), s, z + 0.045))
        if ctx.lod == 0:
            K.box(p, (0.05, 0.004, 0.04), at=(base.x + sx * (reach + 0.02), s - 0.052, z + 0.045), m="veh_trim")
            K.box(p, (0.06, 0.01, 0.006), at=(base.x + sx * (reach + 0.03), s - 0.035, z + 0.073), m=accent)


def calipers(ctx, mat):
    if ctx.lod >= 2:
        return
    sp = ctx.spec
    p = ctx.part("calipers")
    for (s, x) in sp["wheel_pos"]:
        sx = 1 if x > 0 else -1
        zc = sp["wheel_r"]
        r = sp["rim_r"] - 0.05
        cx = x - sx * sp["wheel_w"] * 0.5 * 0.2
        K.box(p, (0.055, 0.15, 0.05), at=(cx, s - 0.0, zc + r - 0.01), m=mat, bevel=0.012, bseg=2)


def wing(ctx, s, z, half, chord=0.22, thick=0.026, angle=-7, pylon_x=0.42, mat="veh_carbon", deck_z=None):
    p = ctx.part("wing")
    prof = [(-chord / 2, 0), (-chord * 0.3, thick * 0.55), (chord * 0.15, thick * 0.5), (chord / 2, thick * 0.08), (chord / 2, -thick * 0.05),
            (0.0, -thick * 0.35), (-chord * 0.4, -thick * 0.25)]
    path = [Vector((-half, 0, 0)), Vector((half, 0, 0))]
    p.begin()
    rings = []
    for c in path:
        rings.append([p.vert(Vector((c.x, -a, b))) for (a, b) in prof])
    K.grid_faces(p, rings, lambda i, j: mat, closed_u=True)
    p.face(list(reversed(rings[0])), mat)
    p.face(rings[1], mat)
    vs = p.end()
    p.transform(Matrix.Translation((0, s, z)) @ Matrix.Rotation(math.radians(angle), 4, "X"), vs)
    if ctx.lod < 2:
        for sx in (-1, 1):
            K.box(p, (0.012, chord * 1.2, 0.12), at=(sx * half, s - 0.01, z - 0.02), m=mat, bevel=0.004)
    dz = deck_z if deck_z is not None else z - 0.12
    for sx in (-1, 1):
        loc, n = ctx.surf.top_z(sx * pylon_x, s + 0.02)
        zb = loc.z - 0.01 if loc else dz
        h = z - zb
        vs = K.box(p, (0.016, 0.10, h), at=(sx * pylon_x, s + 0.02, zb + h / 2), m="veh_trim", bevel=0.005)


def louvres(ctx, s0, s1, n, half, lift=0.02, mat="veh_trim"):
    p = ctx.part("louvres")
    for k in range(n):
        s = s0 + (s1 - s0) * (k + 0.5) / n
        pts = []
        for q in range(9):
            x = -half + 2 * half * q / 8
            loc, nn = ctx.surf.top_z(x, s)
            if loc is not None:
                pts.append(Vector((x, s, loc.z + lift)))
        if len(pts) > 2:
            K.sweep(p, pts, [(-0.03, -0.004), (0.03, -0.004), (0.03, 0.006), (-0.03, 0.01)], m=mat, up=Vector((0, 0, 1)))
    # side rails
    for sx in (-1, 1):
        pts = []
        for q in range(7):
            s = s0 + (s1 - s0) * q / 6
            loc, nn = ctx.surf.top_z(sx * half, s)
            if loc is not None:
                pts.append(Vector((sx * half, s, loc.z + lift * 0.5)))
        if len(pts) > 2:
            K.sweep(p, pts, K.rrect(0.025, 0.02, 0.006, n=1), m=mat, up=Vector((0, 0, 1)))


def plate(ctx, z, sign=-1, w=0.42, h=0.105):
    loc, n = ctx.surf.front_y(0, z, sign)
    if loc is None:
        return
    badge(ctx, loc, Vector((0, sign, 0)), w, h, "plate", raise_=0.006, thick=0.008)


def grille_slats(ctx, s, z0, z1, half, n=4, mat="veh_trim", depth=0.05):
    p = ctx.part("grille")
    for k in range(n):
        z = z0 + (z1 - z0) * (k + 0.5) / n
        xs = [-half + 2 * half * q / 10 for q in range(11)]
        pts = CB.surface_curve(ctx.surf, xs, z, 1, inset=depth)
        if len(pts) > 2:
            K.sweep(p, pts, [(-0.03, -0.004), (0.03, -0.004), (0.03, 0.004), (-0.03, 0.004)], m=mat, up=Vector((0, 0, 1)))


def prism_cutter(poly_yz, x0, x1, m="veh_plastic"):
    """Extrude a (y, z) polygon along X from x0 to x1 -> cutter object."""
    p = K.Part("prism")
    M = Matrix(((0, 0, 1, x0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    K.extrude_poly(p, poly_yz, x1 - x0, M=M, m=m)
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])
    return p.to_object("prism")


def fins_in(ctx, poly_yz, x, n, mat="veh_carbon", depth=0.05, sign=1, along="z"):
    """Vertical fins inside a side intake (polygon bbox), set `depth` inside the surface plane x."""
    p = ctx.part("fins")
    ys = [a for a, b in poly_yz]
    zs = [b for a, b in poly_yz]
    y0, y1, z0, z1 = min(ys), max(ys), min(zs), max(zs)
    for k in range(n):
        t = (k + 0.5) / n
        if along == "z":
            z = z0 + (z1 - z0) * t
            K.box(p, (0.07, (y1 - y0) * 0.95, 0.008), at=(x - sign * depth, (y0 + y1) / 2, z), m=mat, M=Matrix.Rotation(math.radians(sign * 20), 4, "Y"))
        else:
            y = y0 + (y1 - y0) * t
            K.box(p, (0.07, 0.008, (z1 - z0) * 0.95), at=(x - sign * depth, y, (z0 + z1) / 2), m=mat)


# ================================================================================================ assembly
def shell_budget(body, spec, lod):
    """Subdivided shell -> planar cleanup -> collapse decimation to the per-LOD shell budget (symmetric in X)."""
    b = spec.get("shell_tris", 14000) * (1.0, 0.42, 0.12)[lod]
    import os as _os
    if _os.environ.get("VEH_DEBUG"):
        print(f"[shell] {spec['name']} lod{lod} shell {K.tris(body)} budget {int(b)}")
    if K.tris(body) > b:
        md = body.modifiers.new("planar", "DECIMATE")
        md.decimate_type = "DISSOLVE"
        md.angle_limit = math.radians(0.4 if lod == 0 else 1.5)
        md.delimit = {"MATERIAL", "SHARP", "SEAM"}
        K.apply_mods(body)
        # n-gons from the dissolve -> triangles so the collapse metric sees real faces
        with K.Edit(body) as e:
            ng = [f for f in e.bm.faces if len(f.verts) > 4]
            if ng:
                bmesh.ops.triangulate(e.bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
        K.decimate_to(body, int(b), sym=True)
    return body


def build_car(spec, lod):
    K.set_lod(lod)
    ctx = Ctx(spec, lod)
    lower = CB.build_lower(spec, lod)
    # panel gaps on the lower shell (before union so they are cut through clean quads)
    if lod == 0:
        for g in spec.get("grooves", []):
            K.groove_plane(lower, g[0], g[1], g[2], width=g[3] if len(g) > 3 else 0.0035)
    gh = CB.build_greenhouse(spec, lod)
    body = K.boolean(lower, gh, op="UNION")
    if spec.get("post_union"):
        spec["post_union"](ctx, body)
    ctx.surf = K.Surface(body)
    ctx.body = body
    # ---------------------------------------------------------------- cutters
    ctx.cutters += CB.arch_cutters(spec, lod)
    spec["cut"](ctx)
    body = K.boolean(body, ctx.cutters, op="DIFFERENCE")
    shell_budget(body, spec, lod)
    ctx.body = body
    # ---------------------------------------------------------------- details
    ctx.parts.append(CB.arch_lips(spec, ctx.surf, mat=spec.get("lip_mat", "veh_carbon"), lod=lod))
    spec["detail"](ctx)
    if spec.get("cabin"):
        ctx.parts.append(CB.interior(spec, lod))
    objs = [body] + [p.to_object(p.name) for p in ctx.parts if len(p.bm.verts)]
    import os as _os
    if _os.environ.get("VEH_DEBUG"):
        for o in objs:
            lo, hi = K.bounds_world([o])
            print("[part]", o.name, [round(float(x), 2) for x in lo], [round(float(x), 2) for x in hi])
    body = K.join(objs, spec["name"])
    if spec.get("post"):
        spec["post"](ctx, body)
    K.drop_unused_slots(body)
    # ---------------------------------------------------------------- wheels
    wheels = {}
    wspec = spec.get("wheel")
    if wspec:
        for name, (s, x) in zip(("Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"), spec["wheel_order"]):
            wp = WH.build_wheel(R=spec["wheel_r"], W=spec["wheel_w"], rim_r=spec["rim_r"], lod=lod, **wspec)
            if x < 0:
                wp.transform(K.S(-1, 1, 1))
                bmesh.ops.reverse_faces(wp.bm, faces=wp.bm.faces[:])
            wo = wp.to_object(name)
            wheels[name] = (wo, Vector((x, s, spec["wheel_r"])))
    return {"body": body, "wheels": wheels, "lights": ctx.lights, "extra": ctx.extra}


# ================================================================================================ COUPE
def coupe_spec(paint="veh_paint_magenta"):
    """Cab-forward wedge: one rising line from the blade nose over the canopy, blade character line, deep side
    cove into a rear intake, Kamm tail with a full-width light bar, floating blade wing."""
    L = 2.38
    lower = Profile({
        "w": [(-L, 0.95), (-2.30, 0.99), (-2.0, 1.02), (-1.40, 1.035), (-0.95, 1.0), (-0.4, 0.955), (0.4, 0.95), (1.0, 0.975),
              (1.46, 0.985), (1.9, 0.96), (2.2, 0.90), (L, 0.80)],
        "rin": [(-L, 0.06), (-1.4, 0.08), (0.0, 0.10), (1.46, 0.08), (L, 0.05)],
        "zb": [(-L, 0.34), (-2.22, 0.24), (-2.0, 0.15), (-1.6, 0.125), (1.9, 0.115), (2.2, 0.125), (L, 0.15)],
        "zr": [(-L, 0.42), (-2.1, 0.33), (-1.7, 0.27), (1.7, 0.25), (2.2, 0.21), (L, 0.20)],
        "zc": [(-L, 0.70), (-2.0, 0.69), (-1.4, 0.66), (-0.6, 0.58), (0.4, 0.53), (1.46, 0.52), (2.0, 0.42), (L, 0.34)],
        "zs": [(-L, 0.90), (-2.25, 0.925), (-1.8, 0.95), (-1.40, 0.95), (-0.95, 0.89), (-0.4, 0.82), (0.4, 0.78), (1.0, 0.76),
               (1.46, 0.74), (1.85, 0.66), (2.15, 0.55), (L, 0.46)],
        "tin": [(-L, 0.14), (-1.4, 0.13), (-0.4, 0.17), (0.6, 0.17), (1.46, 0.13), (L, 0.12)],
        "zd": [(-L, 0.905), (-2.25, 0.935), (-2.0, 0.93), (-1.6, 0.92), (-1.1, 0.90), (0.6, 0.76), (0.95, 0.72), (1.3, 0.665),
               (1.7, 0.60), (2.05, 0.53), (2.25, 0.475), (L, 0.44)],
        "crown": 0.02,
        "dw": 0.80,
        "fender": 0.2,
    })
    zr_ = [(-1.70, 0.90), (-1.50, 0.955), (-1.25, 1.02), (-0.98, 1.07), (-0.70, 1.10), (-0.42, 1.105), (-0.12, 1.08), (0.18, 1.00),
           (0.46, 0.915), (0.72, 0.83), (0.98, 0.70)]
    gh = Profile({
        "zroof": zr_,
        "zre": [(s_, z_ - 0.03) for s_, z_ in zr_],
        "zw": [(s_, z_ - 0.066) for s_, z_ in zr_[:-1]] + [(0.98, 0.69)],
        "zbelt": [(-1.70, 0.88), (-1.40, 0.90), (-0.95, 0.86), (-0.4, 0.80), (0.4, 0.76), (0.98, 0.69)],
        "xb": [(-1.70, 0.72), (-1.40, 0.80), (-0.95, 0.78), (-0.4, 0.74), (0.4, 0.735), (0.98, 0.69)],
        "xw": [(-1.70, 0.50), (-1.25, 0.58), (-0.6, 0.60), (0.2, 0.585), (0.98, 0.50)],
        "xr": [(-1.70, 0.465), (-1.25, 0.545), (-0.6, 0.565), (0.2, 0.55), (0.98, 0.465)],
        "zbot": 0.55,
    })
    spec = {
        "name": "CyberCar_Coupe", "paint": paint, "subd": 2, "gh_subd": 2,
        "stations": [-L, -2.33, -2.22, -2.0, -1.72, -1.40, -1.05, -0.65, -0.2, 0.25, 0.7, 1.1, 1.46, 1.78, 2.02, 2.2, 2.32, L],
        "lower": lower,
        "lower_creases": {3: 1.0, 4: 1.0, 5: 0.9, 6: 0.5},
        "nose_crease": 0.9, "tail_crease": 1.0,
        "gh_stations": [-1.70, -1.50, -1.25, -0.98, -0.70, -0.42, -0.12, 0.18, 0.46, 0.72, 0.98],
        "gh": gh,
        "gh_zones": {"ws_top": -0.12, "rear_top": -0.70, "side": (-1.0, 1.0), "roof_mat": "veh_carbon", "rear_glass": True,
                     "rail_mat": "veh_trim"},
        "wheel_r": 0.36, "wheel_w": 0.30, "rim_r": 0.26, "arch_r": 0.41,
        "wheel_order": [(1.46, -0.845), (1.46, 0.845), (-1.40, -0.87), (-1.40, 0.87)],
        "wheel": {"style": "aero", "paint": "veh_metal", "accent": "veh_neon"},
        "nose_bulge": 0.03, "tail_bulge": 0.015, "tail_mat": "veh_trim",
        "cabin": {"s0": -0.95, "s1": 0.75, "hw": 0.64, "floor": 0.20, "belt": 0.74, "headliner": (-0.80, -0.15, 1.05, 0.46),
                  "dash_s": 0.55, "dash_z": 0.64, "seat_rows": [(-0.30, (-0.35, 0.35))], "driver_x": -0.35, "yoke_s": 0.28,
                  "yoke_z": 0.66, "seat_h": 0.66, "recline": 26},
        "lip_mat": "veh_carbon",
    }
    spec["wheel_pos"] = spec["wheel_order"]

    def side(c, f):
        return abs(c.x) > 0.62 and c.z > 0.2

    door_f, door_r, sill = 1.0, -0.70, 0.31
    spec["grooves"] = [
        # scissor-door seams: raked front edge, rear edge, sill line
        ((0, door_f, 0.5), (0, math.cos(math.radians(14)), math.sin(math.radians(14))), lambda c: abs(c.x) > 0.6 and 0.30 < c.z < 0.86 and 0.78 < c.y < 1.25),
        ((0, door_r, 0.5), (0, math.cos(math.radians(-10)), math.sin(math.radians(-10))), lambda c: abs(c.x) > 0.6 and 0.30 < c.z < 0.9 and -0.95 < c.y < -0.45),
        ((0, 0, sill), (0, 0, 1), lambda c: abs(c.x) > 0.7 and -0.74 < c.y < 1.04 and 0.2 < c.z < 0.4),
        # front hood: two longitudinal seams + front edge
        ((0.48, 0, 0), (1, 0, 0), lambda c: c.z > 0.5 and 0.95 < c.y < 2.14 and 0.3 < c.x < 0.66),
        ((-0.48, 0, 0), (1, 0, 0), lambda c: c.z > 0.5 and 0.95 < c.y < 2.14 and -0.66 < c.x < -0.3),
        ((0, 2.12, 0), (0, 1, 0), lambda c: c.z > 0.42 and abs(c.x) < 0.50 and 1.95 < c.y < 2.3),
        # rear engine cover
        ((0, -2.06, 0), (0, 1, 0), lambda c: c.z > 0.82 and abs(c.x) < 0.64 and -2.2 < c.y < -1.9),
        ((0.62, 0, 0), (1, 0, 0), lambda c: c.z > 0.82 and -2.1 < c.y < -1.6 and 0.4 < c.x < 0.8),
        ((-0.62, 0, 0), (1, 0, 0), lambda c: c.z > 0.82 and -2.1 < c.y < -1.6 and -0.8 < c.x < -0.4),
        # charge-port flaps on the rear haunches
        ((0, -1.62, 0), (0, 1, 0), lambda c: abs(c.x) > 0.75 and 0.74 < c.z < 0.88 and -1.7 < c.y < -1.5),
        ((0, -1.84, 0), (0, 1, 0), lambda c: abs(c.x) > 0.75 and 0.74 < c.z < 0.88 and -1.95 < c.y < -1.75),
        ((0, 0, 0.765), (0, 0, 1), lambda c: abs(c.x) > 0.75 and -1.85 < c.y < -1.61 and 0.70 < c.z < 0.82),
    ]
    intake = [(-1.0, 0.43), (-0.74, 0.47), (-0.74, 0.66), (-0.90, 0.66)]

    def cut(ctx):
        front_bar(ctx, 0.405, 0.70, 0.024, key="head")
        front_bar(ctx, 0.84, 0.88, 0.032, mat="veh_taillight", sign=-1, key="tail", n=28)
        c = K.Part("intake")
        K.box(c, (1.25, 0.5, 0.12), at=(0, 2.45, 0.235), m="veh_plastic", bevel=0.03)
        # hood vents
        for sx in (-0.29, 0.29):
            vs = K.box(c, (0.17, 0.30, 0.2), m="veh_plastic", bevel=0.02)
            c.transform(Matrix.Translation((sx, 1.72, 0.66)) @ Matrix.Rotation(math.radians(-11), 4, "X"), vs)
        ctx.cutters.append(c.to_object("intake"))
        for sx in (-1, 1):
            ctx.cutters.append(prism_cutter(intake, 0.72 if sx > 0 else -1.3, 1.3 if sx > 0 else -0.72))
        c = K.Part("ports")
        for sx in (-0.42, 0.42):
            K.cyl(c, 0.045, 0.3, n=K.seg(20, 8), axis="Y", m="veh_trim", at=(sx, -2.4, 0.50))
        ctx.cutters.append(c.to_object("ports"))

    def detail(ctx):
        lod = ctx.lod
        grille_slats(ctx, 2.3, 0.19, 0.28, 0.60, n=3)
        splitter(ctx, 0.10, 0.82, 1.95, reach=0.07)
        diffuser(ctx, -2.22, -2.38, 0.19, 0.33, 0.55, fins=5 if lod < 2 else 2)
        underglow(ctx, -0.95, 1.0, 0.82, 0.108, front=(2.0, 0.6))
        if lod < 2:
            mirror_cams(ctx, 0.70, 0.79)
            wing(ctx, -2.15, 1.06, 0.86, pylon_x=0.40)
            louvres(ctx, -1.55, -0.80, 6 if lod == 0 else 3, 0.40, lift=0.022)
            calipers(ctx, "veh_paint_cyan" if paint == "veh_paint_magenta" else "veh_paint_magenta")
            for sx in (-1, 1):
                loc, n = ctx.surf.side_x(-0.87, 0.55, sx)
                xs_ = loc.x if loc else sx * 0.95
                fins_in(ctx, intake, xs_, 4, sign=sx)
            # hood vent fins
            q = ctx.part("hood_fins")
            for sx in (-0.29, 0.29):
                for k in range(4):
                    vs = K.box(q, (0.15, 0.012, 0.05), m="veh_carbon")
                    q.transform(Matrix.Translation((sx, 1.62 + k * 0.065, 0.585 - k * 0.0125)) @ Matrix.Rotation(math.radians(-11), 4, "X")
                                @ Matrix.Rotation(math.radians(35), 4, "X"), vs)
            q = ctx.part("ports")
            for sx in (-0.42, 0.42):
                K.lathe(q, [(0.034, -2.35), (0.04, -2.35), (0.04, -2.38), (0.034, -2.38)], n=K.seg(20, 8), axis="Y", m="veh_neon", closed=True, at=(sx, 0, 0.50))
                K.cyl(q, 0.036, 0.02, n=K.seg(20, 8), axis="Y", m="veh_trim", at=(sx, -2.32, 0.50))
        if lod == 0:
            badge_on(ctx, (0, 2.9, 0.37), (0, -1, 0), 0.10, 0.035, "badge_a")
            badge_on(ctx, (0, -2.9, 0.74), (0, 1, 0), 0.13, 0.045, "badge_a")
            for sx in (-1, 1):
                badge_on(ctx, (sx * 2, 0.80, 0.60), (-sx, 0, 0), 0.10, 0.032, "badge_b")
            plate(ctx, 0.62, -1, w=0.36, h=0.09)
            side_bar(ctx, 0.86, 1.12, 0.60, 0.012, "veh_neon", 1, n=6)
            side_bar(ctx, 0.86, 1.12, 0.60, 0.012, "veh_neon", -1, n=6)
        ctx.extra["lightsNote"] = "Full-width LED bars front (veh_headlight) and rear (veh_taillight); neon fender blades, exhaust-port rings and wheel rings (veh_neon); sill + nose underglow (veh_underglow)."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["colliders"] = [((0, 0, 0.52), (2.0, 4.72, 0.78)), ((0, -0.35, 0.96), (1.2, 1.9, 0.3))]
    return spec


# ================================================================================================ shared: sedan family
def spine(ctx, ranges, x=0.0, w=0.036, h=0.012, mat="veh_chrome"):
    """Raised chrome spine following the top surface along the centre line over given s ranges."""
    p = ctx.part("spine")
    for (s0, s1, n) in ranges:
        pts = []
        for k in range(n + 1):
            s = s0 + (s1 - s0) * k / n
            loc, nn = ctx.surf.top_z(x, s)
            if loc is not None:
                pts.append(Vector((x, s, loc.z - 0.002)))
        if len(pts) > 2:
            K.sweep(p, pts, [(-w / 2, -0.004), (w / 2, -0.004), (w * 0.3, h), (-w * 0.3, h)], m=mat, up=Vector((0, 0, 1)))


def slit_lights(ctx, z, x0, x1, h, mat, sign=1, key="head", depth=0.05, n=8, recess_mat="veh_trim"):
    """Short slit light units at both corners (front sign=+1 / rear -1), following the surface."""
    for sx in (-1, 1):
        xs = [sx * (x0 + (x1 - x0) * k / n) for k in range(n + 1)]
        if sx < 0:
            xs = list(reversed(xs))
        path = CB.surface_curve(ctx.surf, xs, z, sign)
        if len(path) < 3:
            continue
        ctx.cutters.append(CB.slot_cutter(path, h, depth, out=0.1, m=recess_mat, sign=sign, round_r=min(h * 0.45, 0.01)))
        p = ctx.part(f"slit_{key}")
        CB.light_strip(p, path, h * 0.7, 0.012, mat, sign=sign, thick=0.02, round_r=h * 0.3)
        mid = path[len(path) // 2]
        ctx.lights.setdefault(key, []).append([mid.x, mid.y, z])


def light_blade(ctx, z, half, reach=0.07, thick=0.03, mat="veh_taillight", body_mat=None):
    """Rear light blade: a thin full-width fin protruding from the tail with the LED on its trailing edge."""
    xs = [-half + 2 * half * k / 20 for k in range(21)]
    pts = CB.surface_curve(ctx.surf, xs, z, -1)
    if len(pts) < 3:
        return
    p = ctx.part("blade")
    poly = [(c.x, c.y - reach) for c in pts] + [(half * 0.98, pts[-1].y + 0.12), (-half * 0.98, pts[0].y + 0.12)]
    K.extrude_poly(p, poly, thick, M=Matrix.Translation((0, 0, z - thick / 2)), m=body_mat or ctx.spec["paint"])
    q = ctx.part("blade_led")
    path = [Vector((c.x, c.y - reach - 0.004, z)) for c in pts]
    prof = K.rrect(0.012, thick * 0.55, thick * 0.2, n=2)
    vrows = [[q.vert(c + Vector((0, -1, 0)) * a + Vector((0, 0, b))) for (a, b) in prof] for c in path]
    K.grid_faces(q, vrows, lambda i, j: mat, closed_u=True)
    q.face(list(reversed(vrows[0])), mat)
    q.face(vrows[-1], mat)
    ctx.lights.setdefault("tail", []).append([0.0, pts[len(pts) // 2].y - reach, z])


def vgrille(ctx, z0, z1, half, bars=11, mat="veh_chrome", depth=0.06):
    """Recessed grille box (cutter) with vertical chrome bars."""
    c = K.Part("grille_cut")
    zc = (z0 + z1) / 2
    loc, n = ctx.surf.front_y(0, zc, 1)
    y = loc.y if loc else 2.5
    K.box(c, (2 * half, 0.3, z1 - z0), at=(0, y + 0.15 - depth, zc), m="veh_trim", bevel=0.015)
    ctx.cutters.append(c.to_object("grille_cut"))
    p = ctx.part("vgrille")
    for k in range(bars):
        x = -half + 0.03 + (2 * half - 0.06) * k / (bars - 1)
        lc, nn = ctx.surf.front_y(x, zc, 1)
        yy = (lc.y if lc else y) - depth * 0.35
        K.box(p, (0.014, 0.03, (z1 - z0) - 0.02), at=(x, yy, zc), m=mat, bevel=0.004)
    # surround frame
    K.box(p, (2 * half + 0.03, 0.02, 0.018), at=(0, y - 0.004, z1 + 0.006), m=mat, bevel=0.005)
    K.box(p, (2 * half + 0.03, 0.02, 0.018), at=(0, y - 0.004, z0 - 0.006), m=mat, bevel=0.005)


def armour_plates(ctx, s0, s1, z0, z1, mat="veh_metal", n=3):
    """Bolt-on armour plates on the lower doors (raised panels following the side surface)."""
    p = ctx.part("armour")
    for sx in (-1, 1):
        for k in range(n):
            a = s0 + (s1 - s0) * k / n + 0.02
            b = s0 + (s1 - s0) * (k + 1) / n - 0.02
            rows = []
            for zz in (z0, z1):
                pts = CB.side_curve(ctx.surf, [a + (b - a) * q / 4 for q in range(5)], zz, sx)
                rows.append(pts)
            if len(rows[0]) != 5 or len(rows[1]) != 5:
                continue
            outer = [[p.vert(c + Vector((sx * 0.012, 0, 0))) for c in r] for r in rows]
            inner = [[p.vert(c - Vector((sx * 0.01, 0, 0))) for c in r] for r in rows]
            fs = K.grid_faces(p, outer, lambda i, j: mat)
            for (ra, rb) in ((outer[0], inner[0]), (outer[1], inner[1])):
                K.grid_faces(p, [ra, rb], lambda i, j: mat)
            K.grid_faces(p, [[outer[0][0], outer[1][0]], [inner[0][0], inner[1][0]]], lambda i, j: mat)
            K.grid_faces(p, [[outer[0][-1], outer[1][-1]], [inner[0][-1], inner[1][-1]]], lambda i, j: mat)
            if ctx.lod == 0:
                for (yy, zz) in ((a + 0.03, z0 + 0.025), (b - 0.03, z0 + 0.025), (a + 0.03, z1 - 0.025), (b - 0.03, z1 - 0.025)):
                    lc, nn = ctx.surf.side_x(yy, zz, sx)
                    if lc:
                        K.cyl(p, 0.009, 0.03, n=6, axis="X", m="veh_chrome", at=(lc.x + sx * 0.018, yy, zz))
    for f in p.bm.faces:
        pass
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces[:])


# ================================================================================================ SEDAN
def sedan_spec(paint="veh_paint_midnight", name="CyberCar_Sedan"):
    """Armoured executive sedan: long hood, faceted creased panels, slit headlights, chrome spine, rear light blade,
    high armoured beltline with slit side glass, vertical chrome grille, bolt-on door armour."""
    L = 2.62
    lower = Profile({
        "w": [(-L, 0.92), (-2.50, 0.985), (-2.0, 1.01), (-1.55, 1.02), (0, 0.995), (1.62, 1.01), (2.2, 0.995), (2.5, 0.955), (L, 0.90)],
        "rin": 0.05,
        "zb": [(-L, 0.30), (-2.4, 0.20), (-2.0, 0.17), (2.2, 0.17), (2.5, 0.19), (L, 0.24)],
        "zr": [(-L, 0.38), (-2.3, 0.33), (2.3, 0.33), (L, 0.34)],
        "zc": [(-L, 0.76), (-1.55, 0.74), (0, 0.68), (1.62, 0.68), (L, 0.64)],
        "zs": [(-L, 0.98), (-2.4, 1.0), (-1.55, 1.0), (-0.5, 0.975), (0.8, 0.955), (1.62, 0.94), (2.3, 0.89), (L, 0.83)],
        "tin": 0.10,
        "zd": [(-L, 0.985), (-2.45, 1.015), (-2.0, 1.02), (-1.4, 1.0), (1.0, 0.925), (1.6, 0.91), (2.3, 0.865), (L, 0.81)],
        "crown": 0.025,
        "dw": 0.84,
        "fender": 0.15,
    })
    zr_ = [(-1.95, 0.98), (-1.75, 1.08), (-1.45, 1.26), (-1.15, 1.40), (-0.85, 1.44), (-0.45, 1.45), (-0.25, 1.45), (0.0, 1.44),
           (0.25, 1.38), (0.5, 1.24), (0.75, 1.07), (0.98, 0.90)]
    gh = Profile({
        "zroof": zr_,
        "zre": [(s_, z_ - 0.03) for s_, z_ in zr_],
        "zw": [(s_, max(z_ - 0.10, 0.9)) for s_, z_ in zr_],
        "zbelt": [(-1.95, 0.975), (-1.5, 0.985), (0, 0.955), (0.98, 0.90)],
        "xb": [(-1.95, 0.84), (-1.5, 0.87), (0, 0.86), (0.98, 0.84)],
        "xw": [(-1.95, 0.64), (-1.4, 0.71), (0, 0.72), (0.98, 0.66)],
        "xr": [(-1.95, 0.60), (-1.4, 0.675), (0, 0.685), (0.98, 0.62)],
        "zbot": 0.62,
    })
    spec = {
        "name": name, "paint": paint, "subd": 2, "gh_subd": 2,
        "stations": [-L, -2.57, -2.45, -2.2, -1.9, -1.55, -1.15, -0.6, 0.0, 0.6, 1.15, 1.62, 1.95, 2.25, 2.45, 2.57, L],
        "lower": lower,
        "lower_creases": {3: 1.0, 4: 1.0, 5: 1.0, 6: 0.85},
        "nose_crease": 1.0, "tail_crease": 1.0, "nose_bulge": 0.02, "tail_bulge": 0.01,
        "gh_stations": [-1.95, -1.75, -1.45, -1.15, -0.85, -0.45, -0.25, 0.0, 0.25, 0.5, 0.75, 0.98],
        "gh": gh,
        "gh_zones": {"ws_top": 0.25, "rear_top": -1.15, "side": (-1.2, 0.98), "bpillar": (-0.45, -0.25), "bpillar_mat": "veh_trim",
                     "roof_mat": paint, "rear_glass": True, "rail_mat": "veh_chrome"},
        "gh_crease_rail": 1.0,
        "wheel_r": 0.37, "wheel_w": 0.29, "rim_r": 0.27, "arch_r": 0.42,
        "wheel_order": [(1.62, -0.885), (1.62, 0.885), (-1.55, -0.885), (-1.55, 0.885)],
        "wheel": {"style": "multi", "spokes": 6, "paint": "veh_metal"},
        "cabin": {"s0": -1.55, "s1": 0.85, "hw": 0.70, "floor": 0.30, "belt": 0.92, "headliner": (-1.05, 0.12, 1.38, 0.56),
                  "dash_s": 0.70, "dash_z": 0.86, "seat_rows": [(0.05, (-0.37, 0.37)), (-1.0, (-0.37, 0.37))], "driver_x": -0.37,
                  "yoke_s": 0.42, "yoke_z": 0.90, "seat_h": 0.80, "recline": 16},
        "lip_mat": "veh_trim",
        "sill_mat": "veh_metal",
        "shell_tris": 15400,
    }
    door_f, door_m, door_r = 1.14, -0.36, -1.40
    side = lambda lo, hi: (lambda c: abs(c.x) > 0.7 and 0.34 < c.z < 0.99 and lo < c.y < hi)
    spec["grooves"] = [
        ((0, door_f, 0), (0, 1, 0), side(door_f - 0.2, door_f + 0.2)),
        ((0, door_m, 0), (0, 1, 0), side(door_m - 0.2, door_m + 0.2)),
        ((0, door_r, 0), (0, math.cos(math.radians(-6)), math.sin(math.radians(-6))), side(door_r - 0.25, door_r + 0.2)),
        ((0, 0, 0.36), (0, 0, 1), lambda c: abs(c.x) > 0.75 and door_r - 0.02 < c.y < door_f + 0.02 and 0.25 < c.z < 0.45),
        ((0.56, 0, 0), (1, 0, 0), lambda c: c.z > 0.8 and 1.1 < c.y < 2.5 and 0.35 < c.x < 0.75),
        ((-0.56, 0, 0), (1, 0, 0), lambda c: c.z > 0.8 and 1.1 < c.y < 2.5 and -0.75 < c.x < -0.35),
        ((0, 2.48, 0), (0, 1, 0), lambda c: c.z > 0.75 and abs(c.x) < 0.58 and 2.3 < c.y < 2.6),
        ((0, -2.42, 0), (0, 1, 0), lambda c: c.z > 0.85 and abs(c.x) < 0.8 and -2.55 < c.y < -2.25),
        ((0.78, 0, 0), (1, 0, 0), lambda c: c.z > 0.9 and -2.45 < c.y < -1.9 and 0.6 < c.x < 0.9),
        ((-0.78, 0, 0), (1, 0, 0), lambda c: c.z > 0.9 and -2.45 < c.y < -1.9 and -0.9 < c.x < -0.6),
    ]

    def cut(ctx):
        slit_lights(ctx, 0.835, 0.46, 0.90, 0.028, "veh_headlight", 1, "head")
        slit_lights(ctx, 0.79, 0.54, 0.90, 0.016, "veh_headlight", 1, "head_low")
        vgrille(ctx, 0.48, 0.76, 0.36)
        front_bar(ctx, 0.36, 0.72, 0.016, mat="veh_headlight", key="drl", n=20)
        front_bar(ctx, 0.93, 0.86, 0.022, mat="veh_taillight", sign=-1, key="tail_slot", n=24)

    def detail(ctx):
        lod = ctx.lod
        light_blade(ctx, 0.86, 0.90, reach=0.06, thick=0.028)
        splitter(ctx, 0.15, 0.85, 2.25, reach=0.03, thick=0.02, mat="veh_trim", endplates=False)
        underglow(ctx, -1.2, 1.2, 0.86, 0.165, mat="veh_underglow")
        if lod < 2:
            spine(ctx, [(2.58, 0.99, 14), (0.24, -1.14, 10), (-1.96, -2.58, 6)])
            mirror_cams(ctx, 0.82, 0.97, reach=0.09, accent="veh_headlight")
            calipers(ctx, "veh_chrome")
            armour_plates(ctx, -1.36, 1.10, 0.40, 0.58, n=3)
        if lod == 0:
            badge_on(ctx, (0, 3.0, 0.80), (0, -1, 0), 0.12, 0.04, "badge_a")
            badge_on(ctx, (0, -3.0, 0.72), (0, 1, 0), 0.14, 0.045, "badge_a")
            plate(ctx, 0.56, -1, w=0.40, h=0.10)
            plate(ctx, 0.30, 1, w=0.40, h=0.10)
            for sx in (-1, 1):
                badge_on(ctx, (sx * 2, 1.35, 0.78), (-sx, 0, 0), 0.11, 0.035, "badge_b")
        ctx.extra["lightsNote"] = "Twin slit headlights + lower DRL bar (veh_headlight); rear light blade + recessed tail slot (veh_taillight); sill underglow (veh_underglow)."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["colliders"] = [((0, 0, 0.62), (2.0, 5.2, 0.9)), ((0, -0.45, 1.22), (1.5, 2.6, 0.45))]
    spec["wheel_pos"] = spec["wheel_order"]
    return spec


# ================================================================================================ TAXI
def taxi_spec(paint="veh_paint_taxi"):
    """Compact upright cab: short nose, tall glasshouse, yellow body over black lower livery panels with a checker
    band, black roof, roof holo-sign frame (veh_holo_sign), sliding rear door seams, friendly light bar face."""
    L = 2.36
    lower = Profile({
        "w": [(-L, 0.90), (-2.25, 0.96), (-1.42, 0.99), (0, 0.975), (1.45, 0.985), (2.0, 0.96), (2.25, 0.92), (L, 0.86)],
        "rin": 0.05,
        "zb": [(-L, 0.30), (-2.2, 0.21), (2.1, 0.20), (L, 0.26)],
        "zr": [(-L, 0.40), (-2.2, 0.34), (2.2, 0.34), (L, 0.36)],
        "zc": [(-L, 0.64), (-1.42, 0.63), (1.45, 0.62), (L, 0.60)],
        "zs": [(-L, 0.98), (-2.2, 1.0), (-1.42, 0.99), (0.6, 0.95), (1.2, 0.93), (1.8, 0.88), (2.2, 0.82), (L, 0.76)],
        "tin": 0.08,
        "zd": [(-L, 0.98), (-2.2, 1.0), (-1.5, 1.0), (1.0, 0.92), (1.5, 0.89), (2.0, 0.84), (2.25, 0.79), (L, 0.75)],
        "crown": 0.03, "dw": 0.85, "fender": 0.25,
    })
    zr_ = [(-2.12, 0.98), (-2.02, 1.30), (-1.85, 1.52), (-1.55, 1.60), (-0.9, 1.62), (-0.2, 1.62), (0.35, 1.60), (0.62, 1.44),
           (0.88, 1.18), (1.12, 0.90)]
    gh = Profile({
        "zroof": zr_, "zre": [(s, z - 0.035) for s, z in zr_], "zw": [(s, max(z - 0.09, 0.96)) for s, z in zr_],
        "zbelt": [(-2.12, 0.97), (-1.5, 0.985), (0, 0.95), (1.12, 0.90)],
        "xb": [(-2.12, 0.82), (-1.5, 0.88), (0, 0.87), (1.12, 0.84)],
        "xw": [(-2.12, 0.70), (-1.5, 0.76), (0, 0.76), (1.12, 0.70)],
        "xr": [(-2.12, 0.66), (-1.5, 0.725), (0, 0.725), (1.12, 0.66)],
        "zbot": 0.62,
    })
    spec = {
        "name": "CyberCar_Taxi", "paint": paint, "subd": 2, "gh_subd": 2,
        "stations": [-L, -2.31, -2.2, -1.95, -1.42, -0.8, -0.1, 0.6, 1.1, 1.45, 1.8, 2.1, 2.28, L],
        "lower": lower, "lower_creases": {3: 1.0, 4: 1.0, 5: 0.8, 6: 0.5}, "nose_crease": 0.7, "tail_crease": 0.9,
        "nose_bulge": 0.04, "tail_bulge": 0.02,
        "lower_mat_fn": lambda s0, s1, jm: "veh_paint_midnight" if jm == 3 else None,
        "tail_mat": "veh_paint_midnight",
        "gh_stations": [-2.12, -2.02, -1.85, -1.55, -1.2, -0.9, -0.2, 0.05, 0.35, 0.62, 0.88, 1.12],
        "gh": gh,
        "gh_zones": {"ws_top": 0.40, "rear_top": -1.86, "side": (-1.85, 1.12), "bpillar": (-0.2, 0.05), "bpillar_mat": "veh_paint_midnight",
                     "roof_mat": "veh_paint_midnight", "rear_glass": True, "rail_mat": "veh_paint_midnight", "cpillar_mat": "veh_paint_midnight"},
        "wheel_r": 0.35, "wheel_w": 0.27, "rim_r": 0.245, "arch_r": 0.40,
        "wheel_order": [(1.45, -0.86), (1.45, 0.86), (-1.42, -0.86), (-1.42, 0.86)],
        "wheel": {"style": "six", "spokes": 6, "paint": "veh_paint_midnight"},
        "cabin": {"s0": -1.95, "s1": 0.95, "hw": 0.72, "floor": 0.30, "belt": 0.92, "headliner": (-1.45, 0.28, 1.53, 0.60),
                  "dash_s": 0.82, "dash_z": 0.86, "seat_rows": [(0.15, (-0.37, 0.37)), (-1.2, (-0.37, 0.37))], "driver_x": -0.37,
                  "yoke_s": 0.55, "yoke_z": 0.92, "seat_h": 0.82, "recline": 14},
        "lip_mat": "veh_paint_midnight", "sill_mat": "veh_paint_midnight",
    }
    side = lambda lo, hi: (lambda c: abs(c.x) > 0.7 and 0.38 < c.z < 0.99 and lo < c.y < hi)
    spec["grooves"] = [
        ((0, 1.02, 0), (0, 1, 0), side(0.8, 1.25)),
        ((0, -0.1, 0), (0, 1, 0), side(-0.3, 0.1)),
        ((0, -1.05, 0), (0, 1, 0), side(-1.25, -0.85)),
        ((0, 0, 0.40), (0, 0, 1), lambda c: abs(c.x) > 0.75 and -1.07 < c.y < 1.04 and 0.3 < c.z < 0.5),
        ((0, 1.98, 0), (0, 1, 0), lambda c: c.z > 0.7 and abs(c.x) < 0.75 and 1.8 < c.y < 2.15),
        ((0, -2.1, 0), (0, 1, 0), lambda c: c.z > 0.4 and abs(c.x) < 0.75 and -2.25 < c.y < -1.95),
    ]

    def cut(ctx):
        front_bar(ctx, 0.72, 0.74, 0.03, key="head", n=24)
        front_bar(ctx, 0.86, 0.80, 0.045, mat="veh_taillight", sign=-1, key="tail", n=24)
        c = K.Part("grille")
        K.box(c, (1.1, 0.4, 0.14), at=(0, 2.45, 0.46), m="veh_plastic", bevel=0.04)
        ctx.cutters.append(c.to_object("grille"))

    def detail(ctx):
        lod = ctx.lod
        grille_slats(ctx, 2.3, 0.41, 0.51, 0.52, n=2, mat="veh_chrome")
        underglow(ctx, -1.0, 1.0, 0.86, 0.195, mat="veh_underglow")
        # roof holo-sign frame: posts + top bar + double holo panel facing both sides
        loc, n = ctx.surf.top_z(0, -0.6)
        zr0 = loc.z if loc else 1.62
        p = ctx.part("sign")
        K.box(p, (0.10, 1.0, 0.04), at=(0, -0.6, zr0 + 0.015), m="veh_trim", bevel=0.01)
        for sy in (-1.02, -0.18):
            K.box(p, (0.06, 0.05, 0.36), at=(0, sy, zr0 + 0.2), m="veh_trim", bevel=0.01)
        K.box(p, (0.07, 0.92, 0.04), at=(0, -0.6, zr0 + 0.39), m="veh_trim", bevel=0.01)
        K.box(p, (0.03, 0.80, 0.012), at=(0, -0.6, zr0 + 0.405), m="veh_neon")
        q = ctx.part("holo")
        for sx in (-1, 1):
            vs = [q.vert((sx * 0.004, -0.98, zr0 + 0.05)), q.vert((sx * 0.004, -0.22, zr0 + 0.05)),
                  q.vert((sx * 0.004, -0.22, zr0 + 0.36)), q.vert((sx * 0.004, -0.98, zr0 + 0.36))]
            if sx < 0:
                vs = [vs[1], vs[0], vs[3], vs[2]]
            f = q.face(vs, "veh_holo_sign")
            if f:
                for l, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                    l[q.uv].uv = uv
        # livery: checker band decals along both sides at the character line
        for sx in (-1, 1):
            for (y0, y1) in ((1.05, -0.08), (-0.12, -1.02)):
                yc = (y0 + y1) / 2
                lc, nn = ctx.surf.side_x(yc, 0.70, sx)
                if lc:
                    badge(ctx, lc, Vector((sx, 0, 0)), abs(y0 - y1) - 0.03, 0.06, "checker", raise_=0.002, thick=0.003)
        if lod < 2:
            mirror_cams(ctx, 0.98, 0.98, reach=0.09, accent="veh_hazard")
            calipers(ctx, "veh_metal")
            # bumpers (black rubberised)
            for sgn, z in ((1, 0.36), (-1, 0.42)):
                xs = [-0.86 + 1.72 * k / 14 for k in range(15)]
                pts = CB.surface_curve(ctx.surf, xs, z, sgn)
                if len(pts) > 2:
                    pr = ctx.part("bumper")
                    K.sweep(pr, [c + Vector((0, sgn * 0.02, 0)) for c in pts], K.rrect(0.07, 0.10, 0.025, n=2), m="veh_plastic", up=Vector((0, 0, 1)))
        if lod == 0:
            plate(ctx, 0.62, -1, w=0.38, h=0.095)
            plate(ctx, 0.25, 1, w=0.38, h=0.095)
            badge_on(ctx, (0, 3.0, 0.60), (0, -1, 0), 0.10, 0.035, "badge_b")
            for sx in (-1, 1):
                badge_on(ctx, (sx * 2, -1.6, 0.86), (-sx, 0, 0), 0.10, 0.10, "warning")
        ctx.extra["lightsNote"] = "Front light bar (veh_headlight), rear bar (veh_taillight), roof sign (veh_holo_sign additive + veh_neon cap strip), underglow."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["colliders"] = [((0, 0, 0.62), (1.96, 4.72, 0.86)), ((0, -0.45, 1.3), (1.5, 2.9, 0.6))]
    spec["wheel_pos"] = spec["wheel_order"]
    return spec


# ================================================================================================ VAN
def van_spec(paint="veh_paint_gunmetal", name="CyberVan", burnt=False):
    """Forward-control utility van: chamfered box, raked cab glass, sliding cargo door (right), rear barn doors,
    louvred side vents, tubular roof rack with cargo cases + light bar, amber hazard beacons and side markers."""
    L = 2.68
    lower = Profile({
        "w": [(-L, 1.02), (-2.6, 1.05), (2.2, 1.05), (2.5, 1.02), (L, 0.97)],
        "rin": 0.04,
        "zb": [(-L, 0.40), (-2.5, 0.32), (2.4, 0.32), (L, 0.36)],
        "zr": [(-L, 0.48), (-2.5, 0.44), (2.4, 0.44), (L, 0.46)],
        "zc": [(-L, 0.86), (L, 0.80)],
        "zs": [(-L, 1.22), (-2.6, 1.24), (2.2, 1.24), (2.5, 1.18), (L, 1.12)],
        "tin": 0.04,
        "zd": [(-L, 1.22), (-2.6, 1.25), (2.1, 1.25), (2.4, 1.18), (L, 1.10)],
        "crown": 0.02, "dw": 0.92, "fender": 0.3,
    })
    zr_ = [(-2.66, 1.2), (-2.62, 2.20), (-2.5, 2.30), (-1.2, 2.32), (0.8, 2.32), (1.55, 2.28), (1.75, 2.16), (2.02, 1.72), (2.30, 1.26), (2.42, 1.10)]
    gh = Profile({
        "zroof": zr_, "zre": [(s, z - 0.06) for s, z in zr_], "zw": [(s, max(z - 0.12, 1.3)) for s, z in zr_],
        "zbelt": [(-2.66, 1.18), (2.0, 1.21), (2.42, 1.08)],
        "xb": [(-2.66, 1.00), (2.0, 1.01), (2.42, 0.96)],
        "xw": [(-2.66, 0.95), (1.4, 0.95), (2.42, 0.88)],
        "xr": [(-2.66, 0.89), (1.4, 0.89), (2.42, 0.82)],
        "zbot": 0.9,
    })
    glass = "veh_burnt" if burnt else "veh_glass"
    spec = {
        "name": name, "paint": paint, "subd": 2, "gh_subd": 2, "burnt": burnt,
        "stations": [-L, -2.64, -2.5, -1.8, -0.9, 0.0, 0.9, 1.85, 2.3, 2.52, 2.64, L],
        "lower": lower, "lower_creases": {3: 1.0, 4: 1.0, 5: 1.0, 6: 0.8}, "nose_crease": 0.9, "tail_crease": 1.0,
        "nose_bulge": 0.03, "tail_bulge": 0.0,
        "gh_stations": [-2.66, -2.62, -2.5, -1.2, 0.0, 0.8, 1.15, 1.55, 1.75, 2.02, 2.30, 2.42],
        "gh": gh, "gh_crease_rail": 1.0,
        "gh_zones": {"ws_top": 1.76, "rear_top": -2.6, "side": (1.15, 2.42), "roof_mat": paint, "rear_glass": False, "rail_mat": paint,
                     "cpillar_mat": paint},
        "wheel_r": 0.38, "wheel_w": 0.28, "rim_r": 0.26, "arch_r": 0.43,
        "wheel_order": [(1.80, -0.89), (1.80, 0.89), (-1.62, -0.89), (-1.62, 0.89)],
        "wheel": {"style": "steel", "paint": "veh_metal"},
        "cabin": {"s0": 0.95, "s1": 2.25, "hw": 0.88, "floor": 0.48, "belt": 1.18, "headliner": (1.0, 1.6, 2.18, 0.8),
                  "dash_s": 2.10, "dash_z": 1.12, "seat_rows": [(1.35, (-0.48, 0.48))], "driver_x": -0.48, "yoke_s": 1.82,
                  "yoke_z": 1.18, "seat_h": 0.85, "recline": 12, "dash_glow": not burnt},
        "lip_mat": "veh_plastic", "sill_mat": "veh_plastic",
    }
    if burnt:
        for k in ("lip_mat", "sill_mat"):
            spec[k] = "veh_burnt"
        spec["gh_zones"] = dict(spec["gh_zones"], rail_mat="veh_burnt", roof_mat="veh_burnt")
    spec["grooves"] = [
        # sliding cargo door (right side, x>0) + its rail line
        ((0, 0.95, 0), (0, 1, 0), lambda c: c.x > 0.8 and 0.46 < c.z < 2.05 and 0.75 < c.y < 1.15),
        ((0, -0.35, 0), (0, 1, 0), lambda c: c.x > 0.8 and 0.46 < c.z < 2.05 and -0.55 < c.y < -0.15),
        ((0, 0, 2.02), (0, 0, 1), lambda c: c.x > 0.8 and -0.37 < c.y < 0.97 and 1.9 < c.z < 2.15),
        ((0, 0, 1.55), (0, 0, 1), lambda c: c.x > 0.8 and -2.55 < c.y < -0.37 and 1.45 < c.z < 1.65),
        # cab doors both sides
        ((0, 1.15, 0), (0, 1, 0), lambda c: abs(c.x) > 0.8 and 0.46 < c.z < 2.1 and 1.0 < c.y < 1.3),
        ((0, 0, 0.50), (0, 0, 1), lambda c: abs(c.x) > 0.8 and -0.37 < c.y < 2.2 and 0.4 < c.z < 0.6),
        # rear barn doors: centre split + outline
        ((0, 0, 0), (1, 0, 0), lambda c: c.y < -2.55 and 0.45 < c.z < 2.15 and abs(c.x) < 0.2),
        ((0.84, 0, 0), (1, 0, 0), lambda c: c.y < -2.55 and 0.45 < c.z < 2.15 and 0.6 < c.x < 0.95),
        ((-0.84, 0, 0), (1, 0, 0), lambda c: c.y < -2.55 and 0.45 < c.z < 2.15 and -0.95 < c.x < -0.6),
        ((0, 0, 2.12), (0, 0, 1), lambda c: c.y < -2.55 and abs(c.x) < 0.86 and 2.0 < c.z < 2.25),
        # bonnet
        ((0, 2.38, 0), (0, 1, 0), lambda c: c.z > 1.0 and abs(c.x) < 0.9 and 2.2 < c.y < 2.55),
    ]
    vents = []
    for sx in (-1, 1):
        for k in range(5):
            vents.append((sx, -1.85, 1.72 - k * 0.07))

    def cut(ctx):
        front_bar(ctx, 0.98, 0.84, 0.05, key="head", n=24)
        c = K.Part("vent_cut")
        for (sx, y, z) in vents:
            K.box(c, (0.3, 0.62, 0.04), at=(sx * 1.10, y, z), m="veh_trim")
        K.box(c, (1.5, 0.4, 0.2), at=(0, 2.85, 0.68), m="veh_plastic", bevel=0.03)
        ctx.cutters.append(c.to_object("vents"))

    def detail(ctx):
        lod = ctx.lod
        bm = "veh_burnt" if burnt else None
        # louvre blades in the vents
        p = ctx.part("louvres")
        for (sx, y, z) in vents:
            K.box(p, (0.05, 0.6, 0.012), at=(sx * 1.035, y, z - 0.005), m=bm or "veh_metal", M=Matrix.Rotation(math.radians(sx * -30), 4, "Y"))
        grille_slats(ctx, 2.6, 0.62, 0.74, 0.70, n=3, mat=bm or "veh_trim")
        # bumpers
        for sgn, z in ((1, 0.52), (-1, 0.52)):
            xs = [-1.0 + 2.0 * k / 16 for k in range(17)]
            pts = CB.surface_curve(ctx.surf, xs, z, sgn)
            if len(pts) > 2:
                pr = ctx.part("bumper")
                K.sweep(pr, [c + Vector((0, sgn * 0.04, 0)) for c in pts], K.rrect(0.12, 0.16, 0.03, n=2), m=bm or "veh_plastic", up=Vector((0, 0, 1)))
        # rear lights: vertical corner bars, hazard stripes band on the rear bumper
        q = ctx.part("rear_lights")
        for sx in (-1, 1):
            K.box(q, (0.07, 0.03, 0.9), at=(sx * 0.955, -2.69, 1.35), m=bm or "veh_taillight", bevel=0.01)
        ctx.lights.setdefault("tail", []).append([0.0, -2.69, 1.35])
        if not burnt:
            badge(ctx, Vector((0, -2.735, 0.52)), Vector((0, -1, 0)), 1.7, 0.10, "hazard", raise_=0.004, thick=0.004)
        # roof rack
        if lod < 2:
            r = ctx.part("rack")
            zt = 2.32
            for sx in (-0.86, 0.86):
                K.sweep(r, [Vector((sx, -2.35, zt + 0.12)), Vector((sx, 1.45, zt + 0.12))], K.circle(0.025, 8 if lod == 0 else 5), m=bm or "veh_metal")
                for sy in (-2.2, -1.0, 0.2, 1.3):
                    K.box(r, (0.04, 0.06, 0.14), at=(sx, sy, zt + 0.05), m=bm or "veh_trim")
            for k in range(7 if lod == 0 else 4):
                sy = -2.3 + 3.7 * k / (6 if lod == 0 else 3)
                K.sweep(r, [Vector((-0.86, sy, zt + 0.12)), Vector((0.86, sy, zt + 0.12))], K.circle(0.018, 8 if lod == 0 else 5), m=bm or "veh_metal")
            if not burnt:
                K.box(r, (0.9, 0.55, 0.32), at=(-0.3, -1.4, zt + 0.30), m="veh_plastic", bevel=0.03)
                K.box(r, (0.6, 0.5, 0.26), at=(0.42, -0.6, zt + 0.27), m="veh_paint_taxi", bevel=0.03)
                K.box(r, (1.4, 0.10, 0.08), at=(0, 1.42, zt + 0.20), m="veh_trim", bevel=0.015)
                K.box(r, (1.3, 0.02, 0.05), at=(0, 1.475, zt + 0.20), m="veh_headlight")
                for sx in (-0.86, 0.86):
                    for sy in (-2.35, 1.45):
                        K.cyl(r, 0.055, 0.11, n=K.seg(14, 6), axis="Z", m="veh_hazard", at=(sx, sy, zt + 0.24))
                        K.cyl(r, 0.065, 0.03, n=K.seg(14, 6), axis="Z", m="veh_trim", at=(sx, sy, zt + 0.17))
                ctx.lights.setdefault("hazard", []).extend([[sx, sy, zt + 0.24] for sx in (-0.86, 0.86) for sy in (-2.35, 1.45)])
        if not burnt:
            # amber side markers
            for sx in (-1, 1):
                for sy in (2.3, -2.4):
                    lc, nn = ctx.surf.side_x(sy, 0.70, sx)
                    if lc:
                        K.box(ctx.part("markers"), (0.02, 0.12, 0.04), at=(lc.x + sx * 0.005, sy, 0.70), m="veh_hazard")
            underglow(ctx, -1.3, 1.4, 0.92, 0.315, mat="veh_underglow")
        if lod < 2:
            mirror_cams(ctx, 2.18, 1.30, reach=0.14, accent=bm or "veh_hazard")
            calipers(ctx, bm or "veh_metal")
        if lod == 0 and not burnt:
            plate(ctx, 0.78, -1, w=0.40, h=0.10)
            plate(ctx, 0.58, 1, w=0.40, h=0.10)
            badge_on(ctx, (0, 3.5, 0.88), (0, -1, 0), 0.14, 0.045, "badge_a")
            for sx in (-1, 1):
                lc, nn = ctx.surf.side_x(-1.0, 1.25, sx)
                if lc:
                    badge(ctx, lc, Vector((sx, 0, 0)), 2.2, 0.55, "fleet", raise_=0.004, thick=0.004)
        ctx.extra["lightsNote"] = "Front bar + rack light bar (veh_headlight), rear corner bars (veh_taillight), roof beacons + side markers (veh_hazard), underglow."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["colliders"] = [((0, 0, 1.30), (2.1, 5.36, 2.0)), ((0, -0.4, 2.45), (1.8, 4.0, 0.3))]
    spec["wheel_pos"] = spec["wheel_order"]
    if burnt:
        spec["wheel"] = {"style": "steel", "paint": "veh_burnt", "tyre": False}
    return spec
