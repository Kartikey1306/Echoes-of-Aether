"""Flying vehicles: HoverCar_A (spinner, four pod thrusters), HoverCar_B (side ducted fans), HoverTruck (cargo hauler).

No wheels. Thruster pods are separate children `Thruster_*` (pivot at the pod's centre of rotation) whose
nozzle faces are emissive `veh_thruster`. Nav lights use `veh_navlight` (port red / starboard green / white strobes).
"""
import math

import bmesh
from mathutils import Matrix, Vector

import carbody as CB
import vcars as VC
import vkit as K
from vkit import Profile


# ================================================================================================ parts
def nav_light(ctx, centre, kind, size=0.03):
    """Small emissive nav light dome. kind: 'port' (red), 'stbd' (green), 'strobe' (white)."""
    p = ctx.part("nav")
    uv = {"port": (0.25, 0.3), "stbd": (0.75, 0.3), "strobe": (0.5, 0.9)}[kind]
    p.begin()
    K.lathe(p, [(0.0, size * 0.9), (size * 0.6, size * 0.7), (size, 0.0), (size * 0.6, -size * 0.2), (0.0, -size * 0.2)], n=K.seg(10, 6),
            axis="Z", m="veh_navlight", at=tuple(centre))
    vs = p.end()
    K.set_uv_point(p, K.faces_of(vs), uv)


def pod(lod, r=0.22, h=0.20, paint="veh_paint_midnight", vanes=8):
    """Thruster pod centred at its pivot: nacelle (paint), metal collar, honeycomb nozzle + glow ring facing -Z."""
    p = K.Part("pod")
    n = (36, 18, 10)[lod]
    prof = [(0.0, h * 0.62), (r * 0.55, h * 0.6), (r * 0.92, h * 0.42), (r, h * 0.12), (r * 0.98, -h * 0.2), (r * 0.9, -h * 0.4)]
    K.lathe(p, prof, n=n, axis="Z", m=paint)
    K.lathe(p, [(r * 0.9, -h * 0.4), (r * 0.93, -h * 0.5), (r * 0.80, -h * 0.5), (r * 0.78, -h * 0.42)], n=n, axis="Z", m="veh_metal")
    # nozzle: recessed honeycomb disc + bright inner ring
    K.lathe(p, [(r * 0.78, -h * 0.42), (r * 0.62, -h * 0.36), (0.0, -h * 0.36)], n=n, axis="Z", m="veh_thruster")
    if lod < 2:
        K.lathe(p, [(r * 0.80, -h * 0.47), (r * 0.86, -h * 0.47), (r * 0.86, -h * 0.44), (r * 0.80, -h * 0.44)], n=n, axis="Z", m="veh_thruster", closed=True)
        for k in range(vanes if lod == 0 else vanes // 2):
            a = 2 * math.pi * k / vanes
            vs = K.box(p, (r * 1.3, 0.012, 0.035), m="veh_metal")
            p.transform(Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((0, 0, -h * 0.40)) @ Matrix.Rotation(math.radians(25), 4, "X"), vs)
        K.cyl(p, r * 0.16, h * 0.12, n=max(8, n // 3), axis="Z", m="veh_metal", at=(0, 0, -h * 0.40))
    return p


def duct(lod, R=0.36, depth=0.22, paint="veh_paint_midnight"):
    """Ducted fan ring (axis Z, thrust down) for HoverCar_B side thrusters."""
    p = K.Part("duct")
    n = (40, 20, 10)[lod]
    t = 0.05
    prof = [(R, depth / 2), (R + t, depth / 2 - 0.01), (R + t * 1.2, 0.0), (R + t, -depth / 2 + 0.01), (R, -depth / 2), (R - 0.012, 0.0)]
    K.lathe(p, prof, n=n, axis="Z", m=paint, closed=True)
    K.lathe(p, [(R - 0.006, -depth / 2 + 0.005), (R - 0.006, -depth / 2 + 0.03), (R - 0.016, -depth / 2 + 0.03), (R - 0.016, -depth / 2 + 0.005)],
            n=n, axis="Z", m="veh_thruster", closed=True)
    # fan disc (honeycomb glow) + hub + stator blades
    K.lathe(p, [(R - 0.012, -0.02), (R * 0.2, -0.04), (0.0, -0.04)], n=n, axis="Z", m="veh_thruster")
    if lod < 2:
        K.lathe(p, [(R * 0.2, 0.05), (R * 0.22, -0.02), (0.0, -0.03), (0.0, 0.07)], n=max(8, n // 2), axis="Z", m="veh_metal")
        nb = 9 if lod == 0 else 5
        for k in range(nb):
            a = 2 * math.pi * k / nb
            vs = K.box(p, (R * 0.8, 0.014, 0.05), m="veh_metal")
            p.transform(Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((R * 0.6, 0, 0.0)) @ Matrix.Rotation(math.radians(30), 4, "X"), vs)
    return p


def bay_cutters(spec):
    outs = []
    for (name, c, r, top) in spec["pods"]:
        if r <= 0:
            continue
        p = K.Part("bay")
        K.cyl(p, r, 2.0, n=K.seg(32, 10), axis="Z", m="veh_plastic", at=(c[0], c[1], top - 1.0))
        outs.append(p.to_object("bay"))
    return outs


def build_hover(spec, lod):
    K.set_lod(lod)
    ctx = VC.Ctx(spec, lod)
    lower = CB.build_lower(spec, lod)
    if lod == 0:
        for g in spec.get("grooves", []):
            K.groove_plane(lower, g[0], g[1], g[2])
    if spec.get("gh"):
        gh = CB.build_greenhouse(spec, lod)
        body = K.boolean(lower, gh, op="UNION")
    else:
        body = lower
    ctx.surf = K.Surface(body)
    ctx.body = body
    ctx.cutters += bay_cutters(spec)
    spec["cut"](ctx)
    body = K.boolean(body, ctx.cutters, op="DIFFERENCE")
    VC.shell_budget(body, spec, lod)
    spec["detail"](ctx)
    if spec.get("cabin"):
        ctx.parts.append(CB.interior(spec, lod))
    objs = [body] + [p.to_object(p.name) for p in ctx.parts if len(p.bm.verts)]
    body = K.join(objs, spec["name"])
    K.drop_unused_slots(body)
    thr = {}
    for (name, c, r, top) in spec["pods"]:
        kind = spec.get("pod_kind", {}).get(name, "pod")
        if kind == "duct":
            tp = duct(lod, **spec.get("duct_args", {}))
        else:
            args = dict(spec.get("pod_args", {}))
            if r > 0:
                args["r"] = r - 0.03
            tp = pod(lod, **args)
        thr[name] = (tp.to_object(name), Vector(c))
    return {"body": body, "wheels": {}, "thrusters": thr, "lights": ctx.lights, "extra": ctx.extra}


# ================================================================================================ HoverCar_A
def hover_a_spec(paint="veh_paint_pearl"):
    """Police-spinner style flyer: long tapered body, raised rear deck, bubble-ish canopy, four pod thrusters in
    recessed bays at the corners, full-width light bars, nav lights and a roof strobe bar."""
    L = 2.45
    lower = Profile({
        "w": [(-L, 0.62), (-2.3, 0.80), (-1.9, 0.95), (-1.35, 1.0), (-0.4, 0.96), (0.6, 0.94), (1.35, 0.95), (1.9, 0.88), (2.25, 0.74), (L, 0.56)],
        "rin": 0.10,
        "zb": [(-L, 0.62), (-2.25, 0.46), (-1.9, 0.34), (1.9, 0.33), (2.25, 0.42), (L, 0.55)],
        "zr": [(-L, 0.66), (-2.2, 0.54), (-1.8, 0.44), (1.8, 0.43), (2.2, 0.50), (L, 0.60)],
        "zc": [(-L, 0.84), (-1.9, 0.80), (-1.35, 0.74), (0.0, 0.66), (1.35, 0.64), (2.0, 0.62), (L, 0.64)],
        "zs": [(-L, 1.02), (-2.2, 1.06), (-1.6, 1.08), (-1.0, 1.04), (0.0, 0.96), (1.0, 0.90), (1.6, 0.86), (2.1, 0.78), (L, 0.70)],
        "tin": [(-L, 0.10), (-1.35, 0.14), (0.0, 0.18), (1.35, 0.14), (L, 0.10)],
        "zd": [(-L, 1.02), (-2.2, 1.08), (-1.6, 1.09), (-1.1, 1.06), (0.7, 0.92), (1.2, 0.86), (1.8, 0.79), (2.2, 0.73), (L, 0.68)],
        "crown": 0.03, "dw": 0.78, "fender": 0.3,
    })
    zr_ = [(-1.55, 1.02), (-1.30, 1.18), (-1.00, 1.32), (-0.65, 1.42), (-0.30, 1.46), (0.05, 1.44), (0.35, 1.36), (0.62, 1.22),
           (0.88, 1.06), (1.10, 0.88)]
    gh = Profile({
        "zroof": zr_, "zre": [(s, z - 0.04) for s, z in zr_], "zw": [(s, max(z - 0.08, 0.95)) for s, z in zr_],
        "zbelt": [(-1.55, 1.0), (-1.0, 1.0), (0.0, 0.93), (1.10, 0.86)],
        "xb": [(-1.55, 0.70), (-1.0, 0.78), (0.0, 0.76), (1.10, 0.70)],
        "xw": [(-1.55, 0.50), (-0.6, 0.62), (0.3, 0.60), (1.10, 0.50)],
        "xr": [(-1.55, 0.45), (-0.6, 0.57), (0.3, 0.55), (1.10, 0.45)],
        "zbot": 0.7,
    })
    pods = [("Thruster_FL", (-0.74, 1.62, 0.30), 0.25, 0.42), ("Thruster_FR", (0.74, 1.62, 0.30), 0.25, 0.42),
            ("Thruster_RL", (-0.78, -1.55, 0.30), 0.27, 0.43), ("Thruster_RR", (0.78, -1.55, 0.30), 0.27, 0.43)]
    spec = {
        "name": "HoverCar_A", "paint": paint, "subd": 2, "gh_subd": 2,
        "stations": [-L, -2.40, -2.28, -2.05, -1.75, -1.35, -0.9, -0.4, 0.1, 0.6, 1.0, 1.35, 1.7, 2.0, 2.22, 2.38, L],
        "lower": lower, "lower_creases": {3: 1.0, 4: 0.9, 5: 0.7, 6: 0.4}, "nose_crease": 0.7, "tail_crease": 0.9,
        "nose_bulge": 0.05, "tail_bulge": 0.05,
        "lower_mat_fn": lambda s0, s1, jm: "veh_paint_midnight" if jm == 3 else None,
        "gh_stations": [-1.55, -1.30, -1.00, -0.65, -0.30, 0.05, 0.35, 0.62, 0.88, 1.10],
        "gh": gh,
        "gh_zones": {"ws_top": 0.05, "rear_top": -1.0, "side": (-1.3, 1.1), "roof_mat": paint, "rear_glass": True, "rail_mat": "veh_trim"},
        "pods": pods, "pod_args": {"h": 0.22, "paint": "veh_paint_midnight"},
        "sill_mat": "veh_paint_midnight",
        "cabin": {"s0": -1.15, "s1": 0.85, "hw": 0.62, "floor": 0.48, "belt": 0.92, "headliner": (-0.6, 0.2, 1.36, 0.46),
                  "dash_s": 0.70, "dash_z": 0.90, "seat_rows": [(-0.15, (-0.34, 0.34))], "driver_x": -0.34, "yoke_s": 0.45,
                  "yoke_z": 0.94, "seat_h": 0.72, "recline": 20},
    }

    def cut(ctx):
        VC.front_bar(ctx, 0.66, 0.50, 0.03, key="head")
        VC.front_bar(ctx, 0.96, 0.60, 0.034, mat="veh_taillight", sign=-1, key="tail", n=24)
        c = K.Part("vents")
        for sx in (-1, 1):  # side cooling slots ahead of the rear pods
            for k in range(3):
                K.box(c, (0.4, 0.05, 0.03), at=(sx * 1.0, -0.95 - k * 0.075, 0.82), m="veh_trim")
        ctx.cutters.append(c.to_object("vents"))

    def detail(ctx):
        lod = ctx.lod
        VC.underglow(ctx, -1.1, 1.1, 0.84, 0.325, mat="veh_underglow")
        for sx, kind in ((-1, "port"), (1, "stbd")):
            loc, n = ctx.surf.side_x(1.9, 0.66, sx)
            if loc:
                nav_light(ctx, (loc.x + sx * 0.01, 1.9, 0.66), kind)
            loc, n = ctx.surf.side_x(-2.1, 0.92, sx)
            if loc:
                nav_light(ctx, (loc.x + sx * 0.01, -2.1, 0.92), kind)
        if lod < 2:
            # roof strobe/beacon bar
            loc, n = ctx.surf.top_z(0, -0.45)
            z = loc.z if loc else 1.45
            p = ctx.part("roofbar")
            K.box(p, (0.9, 0.16, 0.05), at=(0, -0.45, z + 0.02), m="veh_trim", bevel=0.02)
            K.box(p, (0.3, 0.12, 0.035), at=(-0.28, -0.45, z + 0.06), m="veh_neon", bevel=0.01)
            K.box(p, (0.3, 0.12, 0.035), at=(0.28, -0.45, z + 0.06), m="veh_underglow", bevel=0.01)
            nav_light(ctx, (0, -0.45, z + 0.08), "strobe", size=0.025)
            VC.mirror_cams(ctx, 0.86, 0.95, reach=0.08, accent="veh_neon")
            # canted twin tail fins (swept, thin, carbon) with strobes
            for sx in (-1, 1):
                q = ctx.part("fin")
                poly = [(-2.40, 0.0), (-1.98, 0.0), (-2.26, 0.26), (-2.44, 0.27)]
                vs = VC.K.extrude_poly(q, poly, 0.022, M=Matrix(((0, 0, 1, -0.011), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))), m="veh_carbon")
                loc, n = ctx.surf.top_z(sx * 0.55, -2.2)
                zb = (loc.z - 0.02) if loc else 1.0
                q.transform(Matrix.Translation((sx * 0.55, 0, zb)) @ Matrix.Rotation(math.radians(sx * 18), 4, "Y"), vs)
                nav_light(ctx, (sx * (0.55 + 0.08), -2.42, zb + 0.26), "strobe", size=0.018)
            # under-body heat shield plates
            p = ctx.part("shield")
            K.box(p, (1.2, 2.2, 0.03), at=(0, 0.0, 0.33), m="veh_metal", bevel=0.01)
        if lod == 0:
            VC.badge_on(ctx, (0, 3.0, 0.78), (0, -1, 0), 0.12, 0.04, "badge_b")
            VC.badge_on(ctx, (0, -3.0, 0.85), (0, 1, 0), 0.12, 0.04, "badge_b")
            VC.plate(ctx, 0.78, -1, w=0.34, h=0.085)
            for sx in (-1, 1):
                VC.side_bar(ctx, -0.6, 0.8, 0.70, 0.012, "veh_neon", sx, n=12)
        ctx.extra["lightsNote"] = "Front/rear light bars, roof beacon bar (veh_neon + veh_underglow halves), nav lights + strobes (veh_navlight), pod nozzles (veh_thruster)."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["builder"] = build_hover
    spec["colliders"] = [((0, 0, 0.72), (2.0, 4.8, 0.8)), ((0, -0.25, 1.22), (1.3, 2.4, 0.4))]
    return spec


# ================================================================================================ HoverCar_B
def hover_b_spec(paint="veh_paint_cyan"):
    """Compact two-seat flyer: teardrop pod with a full bubble canopy, two big tilting ducted fans on side
    pylons (Thruster_L/R) and two small rear pods (Thruster_RL/RR)."""
    L = 2.15
    lower = Profile({
        "w": [(-L, 0.30), (-2.0, 0.50), (-1.6, 0.66), (-0.9, 0.74), (0.0, 0.76), (0.9, 0.72), (1.5, 0.62), (1.9, 0.48), (L, 0.30)],
        "rin": 0.10,
        "zb": [(-L, 0.70), (-1.9, 0.52), (-1.4, 0.40), (1.2, 0.40), (1.8, 0.48), (L, 0.62)],
        "zr": [(-L, 0.72), (-1.8, 0.58), (-1.3, 0.48), (1.2, 0.48), (1.8, 0.56), (L, 0.66)],
        "zc": [(-L, 0.80), (-1.5, 0.74), (0.0, 0.68), (1.5, 0.68), (L, 0.72)],
        "zs": [(-L, 0.92), (-1.6, 1.0), (-0.8, 0.98), (0.4, 0.92), (1.4, 0.86), (L, 0.78)],
        "tin": [(-L, 0.06), (0.0, 0.14), (L, 0.06)],
        "zd": [(-L, 0.92), (-1.7, 1.02), (-1.2, 1.02), (0.6, 0.92), (1.4, 0.86), (1.9, 0.82), (L, 0.78)],
        "crown": 0.03, "dw": 0.75, "fender": 0.4,
    })
    zr_ = [(-1.30, 1.0), (-1.05, 1.22), (-0.70, 1.38), (-0.30, 1.44), (0.10, 1.42), (0.45, 1.32), (0.75, 1.14), (1.00, 0.92)]
    gh = Profile({
        "zroof": zr_, "zre": [(s, z - 0.04) for s, z in zr_], "zw": [(s, max(z - 0.07, 0.95)) for s, z in zr_],
        "zbelt": [(-1.30, 0.98), (0.0, 0.92), (1.0, 0.86)],
        "xb": [(-1.30, 0.55), (0.0, 0.62), (1.0, 0.55)],
        "xw": [(-1.30, 0.40), (-0.3, 0.50), (1.0, 0.40)],
        "xr": [(-1.30, 0.34), (-0.3, 0.44), (1.0, 0.34)],
        "zbot": 0.72,
    })
    pods = [("Thruster_L", (-1.20, 0.25, 0.62), 0.0, 0.0), ("Thruster_R", (1.20, 0.25, 0.62), 0.0, 0.0),
            ("Thruster_RL", (-0.42, -1.55, 0.36), 0.20, 0.52), ("Thruster_RR", (0.42, -1.55, 0.36), 0.20, 0.52)]
    spec = {
        "name": "HoverCar_B", "paint": paint, "subd": 2, "gh_subd": 2,
        "stations": [-L, -2.08, -1.92, -1.65, -1.25, -0.7, 0.0, 0.7, 1.25, 1.65, 1.92, 2.08, L],
        "lower": lower, "lower_creases": {3: 0.8, 4: 0.6, 5: 0.5}, "nose_crease": 0.3, "tail_crease": 0.3,
        "nose_bulge": 0.08, "tail_bulge": 0.08,
        "gh_stations": [-1.30, -1.05, -0.70, -0.30, 0.10, 0.45, 0.75, 1.00],
        "gh": gh,
        "gh_zones": {"ws_top": -1.2, "rear_top": -1.2, "side": (-1.3, 1.0), "roof_mat": "veh_glass", "rear_glass": True, "rail_mat": "veh_glass"},
        "pods": pods, "pod_kind": {"Thruster_L": "duct", "Thruster_R": "duct"},
        "duct_args": {"R": 0.36, "depth": 0.24, "paint": "veh_paint_midnight"}, "pod_args": {"h": 0.2, "paint": "veh_paint_midnight"},
        "sill_mat": "veh_carbon",
        "cabin": {"s0": -0.95, "s1": 0.80, "hw": 0.50, "floor": 0.52, "belt": 0.90, "headliner": None,
                  "dash_s": 0.62, "dash_z": 0.90, "seat_rows": [(-0.25, (-0.25, 0.25))], "driver_x": -0.25, "yoke_s": 0.38,
                  "yoke_z": 0.95, "seat_h": 0.70, "recline": 20},
    }

    def cut(ctx):
        VC.front_bar(ctx, 0.74, 0.36, 0.028, key="head", n=16)
        VC.front_bar(ctx, 0.90, 0.40, 0.03, mat="veh_taillight", sign=-1, key="tail", n=16)

    def detail(ctx):
        lod = ctx.lod
        VC.underglow(ctx, -0.9, 0.9, 0.62, 0.392, mat="veh_underglow")
        # duct pylons (static) from the body sides to the duct rings
        p = ctx.part("pylons")
        for sx in (-1, 1):
            loc, n = ctx.surf.side_x(0.25, 0.70, sx)
            x0 = loc.x - sx * 0.05 if loc else sx * 0.7
            K.box(p, (abs(1.20 - 0.40 - abs(x0)) + 0.4, 0.22, 0.07), at=(sx * (abs(x0) + 1.20 - 0.40) / 2 + sx * 0.0, 0.25, 0.70), m="veh_carbon", bevel=0.02)
            nav_light(ctx, (sx * 1.60, 0.25, 0.64), "port" if sx < 0 else "stbd")
        if lod < 2:
            VC.mirror_cams(ctx, 0.70, 0.93, reach=0.06, accent="veh_neon")
            q = ctx.part("tailfin")
            poly = [(-2.10, 0.92), (-1.55, 0.98), (-1.95, 1.30), (-2.18, 1.32)]
            K.extrude_poly(q, poly, 0.03, M=Matrix(((0, 0, 1, -0.015), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))), m=ctx.spec["paint"])
            nav_light(ctx, (0, -2.16, 1.32), "strobe", size=0.02)
        if lod == 0:
            VC.badge_on(ctx, (0, 3.0, 0.80), (0, -1, 0), 0.10, 0.034, "badge_b")
            for sx in (-1, 1):
                VC.side_bar(ctx, -1.2, -0.2, 0.74, 0.012, "veh_neon", sx, n=8)
        ctx.extra["lightsNote"] = "Ducted fans Thruster_L/R tilt about their local X (pivot at the duct centre); rear pods Thruster_RL/RR."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["builder"] = build_hover
    spec["colliders"] = [((0, 0, 0.72), (1.6, 4.3, 0.75)), ((0, -0.15, 1.18), (1.1, 2.0, 0.5)), ((0, 0.25, 0.65), (3.2, 0.8, 0.3))]
    return spec


# ================================================================================================ HoverTruck
def hover_truck_spec(paint="veh_paint_gunmetal"):
    """Heavy flying cargo hauler (~9.4 m): faceted cab module with a wraparound visor, ribbed cargo container with
    fleet markings, six thruster pods, hazard beacons, nav lights, light bars."""
    L = 4.7
    lower = Profile({
        "w": [(-L, 1.20), (-4.6, 1.26), (-3.0, 1.28), (2.0, 1.28), (3.2, 1.26), (4.2, 1.18), (4.55, 1.05), (L, 0.92)],
        "rin": 0.08,
        "zb": [(-L, 0.75), (-4.5, 0.62), (4.3, 0.60), (4.6, 0.72), (L, 0.85)],
        "zr": [(-L, 0.85), (-4.4, 0.75), (4.2, 0.74), (4.6, 0.85), (L, 0.95)],
        "zc": [(-L, 1.5), (3.0, 1.5), (4.2, 1.45), (L, 1.35)],
        "zs": [(-L, 3.2), (-4.55, 3.28), (2.4, 3.28), (2.6, 2.2), (3.0, 1.95), (4.2, 1.85), (L, 1.62)],
        "tin": [(-L, 0.05), (2.4, 0.05), (2.8, 0.12), (L, 0.16)],
        "zd": [(-L, 3.24), (-4.55, 3.32), (2.4, 3.32), (2.6, 2.25), (3.0, 1.98), (4.2, 1.86), (L, 1.62)],
        "crown": 0.03, "dw": 0.9, "fender": 0.2,
    })
    zr_ = [(2.15, 2.0), (2.45, 2.6), (2.85, 3.02), (3.35, 3.12), (3.85, 3.02), (4.25, 2.62), (4.55, 2.0)]
    gh = Profile({
        "zroof": zr_, "zre": [(s, z - 0.05) for s, z in zr_], "zw": [(s, max(z - 0.30, 2.0)) for s, z in zr_],
        "zbelt": [(2.15, 1.95), (4.55, 1.80)],
        "xb": [(2.15, 1.16), (3.5, 1.12), (4.55, 0.95)],
        "xw": [(2.15, 1.04), (3.5, 1.02), (4.55, 0.86)],
        "xr": [(2.15, 0.96), (3.5, 0.94), (4.55, 0.78)],
        "zbot": 1.5,
    })
    pods = [("Thruster_FL", (-1.15, 3.55, 0.42), 0.34, 0.72), ("Thruster_FR", (1.15, 3.55, 0.42), 0.34, 0.72),
            ("Thruster_ML", (-1.20, 0.2, 0.42), 0.36, 0.70), ("Thruster_MR", (1.20, 0.2, 0.42), 0.36, 0.70),
            ("Thruster_RL", (-1.20, -3.4, 0.42), 0.36, 0.72), ("Thruster_RR", (1.20, -3.4, 0.42), 0.36, 0.72)]
    spec = {
        "name": "HoverTruck", "paint": paint, "subd": 2, "gh_subd": 1,
        "stations": [-L, -4.66, -4.5, -3.5, -2.0, -0.5, 1.0, 2.2, 2.4, 2.55, 2.75, 3.1, 3.6, 4.1, 4.4, 4.6, L],
        "lower": lower, "lower_creases": {3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}, "nose_crease": 1.0, "tail_crease": 1.0,
        "nose_bulge": 0.04, "tail_bulge": 0.0,
        "gh_stations": [2.15, 2.45, 2.85, 3.35, 3.85, 4.25, 4.55],
        "gh": gh,
        "gh_zones": {"ws_top": 3.85, "rear_top": 2.4, "side": (2.6, 4.55), "roof_mat": paint, "rear_glass": False, "rail_mat": "veh_trim",
                     "cpillar_mat": paint},
        "pods": pods, "pod_args": {"h": 0.30, "paint": "veh_metal", "vanes": 10},
        "sill_mat": "veh_metal",
        "cabin": {"s0": 2.55, "s1": 4.2, "hw": 1.0, "floor": 1.05, "belt": 1.84, "headliner": (2.7, 3.9, 2.8, 0.85),
                  "dash_s": 4.0, "dash_z": 1.78, "seat_rows": [(3.2, (-0.48, 0.48))], "driver_x": -0.48, "yoke_s": 3.72,
                  "yoke_z": 1.84, "seat_h": 0.85, "recline": 15},
    }
    spec["grooves"] = []
    for s in (-3.3, -1.9, -0.5, 0.9):  # container panel seams
        spec["grooves"].append(((0, s, 0), (0, 1, 0), (lambda c: abs(c.x) > 1.1 and 0.9 < c.z < 3.2)))

    def cut(ctx):
        VC.front_bar(ctx, 1.30, 0.92, 0.04, key="head", n=24)
        VC.front_bar(ctx, 0.98, 0.70, 0.03, mat="veh_headlight", key="head_low", n=20)
        c = K.Part("rear")
        K.box(c, (2.2, 0.3, 2.2), at=(0, -4.80, 2.0), m="veh_trim", bevel=0.05)
        ctx.cutters.append(c.to_object("rear"))

    def detail(ctx):
        lod = ctx.lod
        p = ctx.part("ribs")
        if lod < 2:
            # container ribs (vertical stiffeners) both sides
            for sx in (-1, 1):
                for k in range(14 if lod == 0 else 7):
                    s = -4.3 + k * (6.4 / ((14 if lod == 0 else 7) - 1))
                    loc, n = ctx.surf.side_x(s, 2.25, sx)
                    if loc:
                        K.box(p, (0.05, 0.08, 1.7), at=(loc.x + sx * 0.02, s, 2.25), m="veh_metal", bevel=0.01)
            # rear doors with lock bars
            for sx in (-0.5, 0.5):
                K.box(p, (1.0, 0.04, 2.1), at=(sx, -4.64, 2.0), m=ctx.spec["paint"], bevel=0.01)
                for bx in (-0.25, 0.25):
                    K.cyl(p, 0.022, 2.0, n=8, axis="Z", m="veh_chrome", at=(sx + bx, -4.68, 2.0))
            # roof gear: beacons + antenna
            for sx in (-1, 1):
                for sy in (-4.4, 2.3):
                    K.cyl(p, 0.07, 0.12, n=K.seg(14, 6), axis="Z", m="veh_hazard", at=(sx * 1.05, sy, 3.40))
                    K.cyl(p, 0.085, 0.03, n=K.seg(14, 6), axis="Z", m="veh_trim", at=(sx * 1.05, sy, 3.33))
            VC.mirror_cams(ctx, 4.05, 1.95, reach=0.15, accent="veh_hazard")
        # cargo markings on the container sides (decal: fleet strip) + hazard band at the rear
        for sx in (-1, 1):
            loc, n = ctx.surf.side_x(-1.0, 2.6, sx)
            if loc:
                VC.badge(ctx, Vector((loc.x + sx * 0.01, -1.0, 2.6)), Vector((sx, 0, 0)), 3.4, 0.85, "fleet", raise_=0.006, thick=0.006)
        VC.badge(ctx, Vector((0, -4.69, 0.98)), Vector((0, -1, 0)), 2.2, 0.28, "hazard", raise_=0.005, thick=0.006)
        for sx, kind in ((-1, "port"), (1, "stbd")):
            nav_light(ctx, (sx * 1.30, 4.0, 1.5), kind, size=0.04)
            nav_light(ctx, (sx * 1.30, -4.6, 3.25), kind, size=0.04)
        nav_light(ctx, (0, -4.55, 3.36), "strobe", size=0.035)
        # tail lights: vertical bars at rear corners
        q = ctx.part("tails")
        for sx in (-1, 1):
            K.box(q, (0.08, 0.04, 1.6), at=(sx * 1.16, -4.72, 2.1), m="veh_taillight", bevel=0.01)
        ctx.lights.setdefault("tail", []).append([0.0, -4.72, 2.1])
        VC.underglow(ctx, -4.0, 4.0, 1.2, 0.595, mat="veh_underglow")
        if lod == 0:
            VC.badge_on(ctx, (0, 6.0, 1.6), (0, -1, 0), 0.25, 0.08, "badge_a")
            VC.plate(ctx, 0.85, 1, w=0.5, h=0.125)
        ctx.extra["lightsNote"] = "Cab light bars (veh_headlight), rear corner bars (veh_taillight), roof beacons (veh_hazard), nav lights + strobe (veh_navlight), six pods (veh_thruster)."

    spec["cut"] = cut
    spec["detail"] = detail
    spec["builder"] = build_hover
    spec["colliders"] = [((0, -1.1, 2.0), (2.6, 7.2, 2.6)), ((0, 3.4, 1.8), (2.5, 2.4, 2.4))]
    return spec
