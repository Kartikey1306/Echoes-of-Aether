"""CyberBike: heavy hubless-wheel motorcycle with glowing rims.

Body = lofted subdivision fairing (carbody lower ring), hugging the wheel tops; hubless wheels are separate
children Wheel_F / Wheel_R (pivot = wheel centre, spin about local X). Static C-arms hold the inner bearing rings.
"""
import math

import bmesh
from mathutils import Matrix, Vector

import carbody as CB
import vcars as VC
import vkit as K
import wheels as WH
from vkit import Profile

WF = (0.0, 0.98, 0.40)   # front wheel centre (build space)
WR = (0.0, -0.86, 0.42)  # rear wheel centre
RF, RR = 0.40, 0.42
WF_W, WR_W = 0.20, 0.27


def bike_spec(paint="veh_paint_midnight"):
    lower = Profile({
        "w": [(-1.32, 0.06), (-1.25, 0.13), (-1.05, 0.19), (-0.86, 0.20), (-0.55, 0.22), (-0.2, 0.26), (0.15, 0.30), (0.45, 0.29),
              (0.75, 0.21), (0.98, 0.17), (1.22, 0.13), (1.34, 0.07)],
        "rin": [(-1.32, 0.01), (0.0, 0.06), (1.34, 0.01)],
        "zb": [(-1.32, 0.86), (-1.1, 0.86), (-0.86, 0.87), (-0.62, 0.80), (-0.48, 0.58), (-0.38, 0.34), (0.0, 0.27), (0.42, 0.33),
               (0.56, 0.62), (0.70, 0.82), (0.98, 0.86), (1.25, 0.80), (1.34, 0.74)],
        "zr": [(-1.32, 0.88), (-0.86, 0.90), (-0.62, 0.84), (-0.48, 0.64), (-0.38, 0.42), (0.0, 0.36), (0.42, 0.42), (0.56, 0.68),
               (0.70, 0.86), (0.98, 0.89), (1.34, 0.77)],
        "zc": [(-1.32, 0.92), (-0.86, 0.95), (-0.5, 0.80), (0.0, 0.60), (0.5, 0.78), (0.98, 0.93), (1.34, 0.80)],
        "zs": [(-1.32, 0.97), (-1.0, 1.02), (-0.7, 0.98), (-0.45, 0.86), (-0.1, 0.92), (0.25, 1.02), (0.55, 1.04), (0.8, 1.0),
               (1.1, 0.94), (1.34, 0.83)],
        "tin": [(-1.32, 0.02), (-0.4, 0.06), (0.3, 0.09), (1.34, 0.03)],
        "zd": [(-1.32, 0.98), (-1.0, 1.04), (-0.72, 1.0), (-0.45, 0.87), (-0.1, 0.94), (0.25, 1.05), (0.55, 1.07), (0.8, 1.02),
               (1.1, 0.95), (1.34, 0.84)],
        "crown": 0.02, "dw": 0.7, "fender": 0.3,
    })
    return {
        "name": "CyberBike", "paint": paint, "subd": 2,
        "stations": [-1.32, -1.28, -1.18, -1.0, -0.86, -0.7, -0.55, -0.45, -0.3, -0.1, 0.15, 0.4, 0.55, 0.7, 0.85, 1.0, 1.15, 1.27, 1.34],
        "lower": lower, "lower_creases": {3: 0.6, 4: 1.0, 5: 0.8}, "nose_crease": 0.6, "tail_crease": 0.9,
        "nose_bulge": 0.02, "tail_bulge": 0.02, "sill_mat": "veh_carbon",
        "builder": build_bike, "shell_tris": 7000,
        "colliders": [((0, 0.05, 0.62), (0.62, 2.7, 0.9))],
    }


def c_arm(p, centre, R, a0, a1, width, mat="veh_metal", n=12, side=0.0):
    """Static inner bearing arc of a hubless wheel (radius R about X through centre, angles a0..a1 degrees)."""
    path = []
    for k in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * k / n)
        path.append(Vector((centre[0] + side, centre[1] + R * math.cos(a), centre[2] + R * math.sin(a))))
    K.sweep(p, path, K.rrect(width, 0.05, 0.015, n=2), m=mat, up=Vector((1, 0, 0)))
    return path


def build_bike(spec, lod):
    K.set_lod(lod)
    ctx = VC.Ctx(spec, lod)
    body = CB.build_lower(spec, lod)
    if lod == 0:
        K.groove_plane(body, (0, 0.25, 0), (0, 1, 0), lambda c: c.z > 0.9 and -0.2 < c.y < 0.7)
        K.groove_plane(body, (0, 0, 0.62), (0, 0, 1), lambda c: abs(c.x) > 0.18 and -0.4 < c.y < 0.5)
    ctx.surf = K.Surface(body)
    ctx.body = body
    VC.front_bar(ctx, 0.86, 0.10, 0.022, key="head", n=8)
    VC.front_bar(ctx, 0.94, 0.06, 0.03, mat="veh_taillight", sign=-1, key="tail", n=6)
    body = K.boolean(body, ctx.cutters, op="DIFFERENCE")
    VC.shell_budget(body, spec, lod)
    p = ctx.part("frame")
    # inner bearing C-arms (static) for both wheels + connecting struts into the body
    for (c, R, W, a0, a1) in ((WF, RF, WF_W, 20, 160), (WR, RR, WR_W, 20, 160)):
        rin = R - 0.085 - 0.06
        for sx in (-1, 1):
            c_arm(p, c, rin, a0, a1, 0.035, side=sx * (W / 2 - 0.03), n=K.seg(14, 6))
        K.box(p, (W - 0.02, 0.10, 0.06), at=(0, c[1], c[2] + rin + 0.02), m="veh_metal", bevel=0.01)
    # front fork blades from the nose to the bearing arms
    for sx in (-1, 1):
        K.sweep(p, [Vector((sx * 0.09, 0.62, 0.86)), Vector((sx * 0.085, 0.80, 0.76)), Vector((sx * 0.085, 0.93, 0.70))],
                K.rrect(0.03, 0.06, 0.012, n=1), m="veh_chrome", up=Vector((1, 0, 0)))
    # rear swingarm (single-sided look on the right) + battery heat-sink fins
    K.sweep(p, [Vector((0.15, -0.30, 0.45)), Vector((0.16, -0.62, 0.55)), Vector((0.15, -0.80, 0.67))], K.rrect(0.05, 0.10, 0.02, n=2),
            m="veh_metal", up=Vector((1, 0, 0)))
    if lod < 2:
        for sx in (-1, 1):
            for k in range(6):
                K.box(p, (0.012, 0.36, 0.05), at=(sx * 0.255, 0.02, 0.42 + k * 0.035), m="veh_metal")
    # seat, clip-on bars, screen, pegs
    q = ctx.part("seat")
    seat = []
    for k in range(7):
        s = -0.78 + 0.62 * k / 6
        loc, n = ctx.surf.top_z(0, s)
        seat.append(Vector((0, s, (loc.z if loc else 0.9) + 0.01)))
    K.sweep(q, seat, K.rrect(0.30, 0.07, 0.03, n=2), m="veh_interior", up=Vector((0, 0, 1)))
    r = ctx.part("controls")
    for sx in (-1, 1):
        K.sweep(r, [Vector((sx * 0.12, 0.47, 1.02)), Vector((sx * 0.26, 0.42, 1.00)), Vector((sx * 0.33, 0.38, 0.99))], K.circle(0.016, 6), m="veh_trim",
                up=Vector((0, 0, 1)))
        K.cyl(r, 0.021, 0.10, n=8, axis="X", m="veh_rubber", at=(sx * 0.37, 0.375, 0.99))
        K.box(r, (0.05, 0.14, 0.02), at=(sx * 0.17, -0.25, 0.42), m="veh_metal", bevel=0.005)
    scr = ctx.part("screen")
    pts = [Vector((-0.17, 0.62, 1.05)), Vector((0.17, 0.62, 1.05)), Vector((0.12, 0.50, 1.20)), Vector((-0.12, 0.50, 1.20))]
    vs = [scr.vert(v) for v in pts]
    scr.face(vs, "veh_glass")
    scr.face(list(reversed([scr.vert(v + Vector((0, 0.004, -0.002))) for v in pts])), "veh_glass")
    # neon side stripes + underglow + dash glow
    for sx in (-1, 1):
        VC.side_bar(ctx, -1.15, 1.18, 0.95 if sx else 0.95, 0.012, "veh_neon", sx, n=16) if False else None
    neon = ctx.part("neon")
    for sx in (-1, 1):
        path = []
        for k in range(15):
            s = -1.1 + 2.25 * k / 14
            loc, n = ctx.surf.side_x(s, ctx.spec["lower"]("zc", s), sx)
            if loc:
                path.append(Vector((loc.x + sx * 0.004, s, ctx.spec["lower"]("zc", s))))
        if len(path) > 2:
            K.sweep(neon, path, K.rrect(0.006, 0.012, 0.003, n=1), m="veh_neon", up=Vector((0, 0, 1)))
    VC.underglow(ctx, -0.3, 0.38, 0.12, 0.265, mat="veh_underglow", w=0.03)
    if lod == 0:
        VC.badge_on(ctx, (0.6, 0.3, 0.80), (-1, 0, 0), 0.12, 0.04, "badge_b")
        VC.badge_on(ctx, (-0.6, 0.3, 0.80), (1, 0, 0), 0.12, 0.04, "badge_b")
        VC.plate(ctx, 0.84, -1, w=0.18, h=0.045)
    objs = [body] + [pp.to_object(pp.name) for pp in ctx.parts if len(pp.bm.verts)]
    body = K.join(objs, spec["name"])
    K.drop_unused_slots(body)
    wheels = {}
    for name, c, R, W in (("Wheel_F", WF, RF, WF_W), ("Wheel_R", WR, RR, WR_W)):
        wp = WH.build_hubless(R=R, W=W, lod=lod)
        wheels[name] = (wp.to_object(name), Vector(c))
    ctx.extra["lightsNote"] = "Nose slit (veh_headlight), tail slit (veh_taillight), hubless rim glow + side stripes (veh_neon), belly underglow."
    return {"body": body, "wheels": wheels, "lights": ctx.lights, "extra": ctx.extra}
