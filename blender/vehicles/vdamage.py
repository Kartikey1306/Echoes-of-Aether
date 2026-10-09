"""Damage passes for the wrecked / burnt variants: crumple, dents, broken glass, missing / flat wheels, tilt,
fire-gutting (material remap + open windows + sag)."""
import math
import random

import bmesh
from mathutils import Matrix, Vector, noise

import vcars as VC
import vkit as K


def _noise3(v, scale, seed):
    return noise.noise(Vector((v.x * scale + seed * 7.1, v.y * scale - seed * 3.3, v.z * scale + seed * 1.7)))


def deform(ob, fn):
    with K.Edit(ob) as e:
        for v in e.bm.verts:
            v.co = fn(v.co.copy())


def wreck_shell(ctx, body):
    """Called after the greenhouse union (before detail placement) so details follow the damage."""
    def fn(c):
        out = c.copy()
        # front crumple: front 0.9 m shortened + buckled, heavier on the left (driver) corner
        if c.y > 1.75:
            t = (c.y - 1.75) / 0.9
            k = 0.30 + 0.12 * max(0.0, -c.x)
            out.y = c.y - t * t * 0.9 * k
            out.z = c.z + 0.05 * math.sin(math.pi * min(t, 1.0)) * (1 if c.z > 0.7 else -0.4)
            n = _noise3(c, 7.0, 1)
            out += Vector((n * 0.03, _noise3(c, 6.0, 2) * 0.035, _noise3(c, 6.5, 3) * 0.03)) * min(1.0, t * 1.5)
        # roof dent
        d = Vector((c.x - 0.25, c.y + 0.6, 0)).length
        if c.z > 1.25 and d < 0.75:
            out.z -= 0.10 * (1 - d / 0.75) ** 1.5
        # side dents (left rear door, right front fender)
        for (cx, cy, cz, r, depth) in ((-1.0, -0.9, 0.62, 0.35, 0.06), (1.0, 1.5, 0.75, 0.3, 0.05)):
            dd = Vector((0, c.y - cy, c.z - cz)).length
            if dd < r and c.x * cx > 0.5:
                out.x -= math.copysign(depth * (1 - dd / r) ** 2, cx)
        # overall low-frequency warping
        out += Vector((_noise3(c, 1.6, 5), _noise3(c, 1.6, 6), _noise3(c, 1.6, 7))) * 0.008
        return out
    deform(body, fn)


def break_glass(ob, seed=4, hole_fn=None):
    """veh_glass -> veh_glass_cracked; delete glass faces where hole_fn(centre) is True (shattered holes)."""
    with K.Edit(ob) as e:
        gi = e.slot("veh_glass")
        ci = e.slot("veh_glass_cracked")
        kill = []
        for f in e.bm.faces:
            if f.material_index == gi:
                c = f.calc_center_median()
                if hole_fn and hole_fn(c):
                    kill.append(f)
                else:
                    f.material_index = ci
        bmesh.ops.delete(e.bm, geom=kill, context="FACES")
    K.drop_unused_slots(ob)


def wrecked_builder(spec, lod):
    res = VC.build_car(spec, lod)
    body = res["body"]
    rnd = random.Random(11)

    def holes(c):
        # windscreen: shattered on the driver side; driver window gone; rear-left window partly gone
        if c.y > 0.3 and c.z > 1.0 and c.x < 0.15 and _noise3(c, 9.0, 3) > -0.15:
            return True
        if c.x < -0.6 and -0.3 < c.y < 0.9 and c.z > 1.0:
            return True
        if c.x < -0.6 and c.y < -0.4 and _noise3(c, 8.0, 9) > 0.1:
            return True
        return False
    break_glass(body, hole_fn=holes)
    # wheels: FL missing (hub on the ground), FR flat, rears stay; merged into the static mesh
    keep = []
    for name, (wo, c) in res["wheels"].items():
        if name == "Wheel_FL":
            continue
        if name == "Wheel_FR":
            deform(wo, lambda v: Vector((v.x * (1.0 + 0.25 * max(0.0, -v.z - 0.24) / 0.13), v.y, max(v.z, -0.27 + 0.02 * abs(v.y)))))
        wo.data.transform(Matrix.Translation(c))
        keep.append(wo)
    if lod < 2:
        # bare hub stub where FL wheel was
        p = K.Part("hub")
        wr = spec["wheel_r"]
        K.cyl(p, 0.11, 0.12, n=K.seg(16, 8), axis="X", m="veh_metal", at=(-0.80, 1.62, wr))
        K.cyl(p, 0.19, 0.03, n=K.seg(24, 8), axis="X", m="veh_metal", at=(-0.76, 1.62, wr))
        keep.append(p.to_object("hub"))
    body = K.join([body] + keep, spec["name"])
    # settle: the FL corner drops onto the hub (hub bottom ~ wheel_r - 0.19 below centre)
    drop = spec["wheel_r"] - 0.19 + 0.0
    with K.Edit(body) as e:
        for v in e.bm.verts:
            # bilinear drop field: 1 at FL corner, 0 at the opposite axle/side
            fx = min(1.0, max(0.0, (-v.co.x + 0.9) / 1.8))
            fy = min(1.0, max(0.0, (v.co.y + 1.55) / 3.17))
            v.co.z -= drop * fx * fy
    # re-ground
    lo, hi = K.bounds_world([body])
    body.data.transform(Matrix.Translation((0, 0, -lo[2])))
    # small debris: bent bumper strip + glass shards near the front
    p = K.Part("debris")
    K.box(p, (0.7, 0.05, 0.10), at=(-0.4, 2.72, 0.025), m="veh_paint_wrecked", M=Matrix.Rotation(math.radians(18), 4, "Z") @ Matrix.Rotation(math.radians(80), 4, "X"))
    for k in range(10 if lod == 0 else 3):
        x, y = rnd.uniform(-1.0, 0.6), rnd.uniform(2.3, 2.9)
        vs = K.box(p, (rnd.uniform(0.03, 0.08), rnd.uniform(0.03, 0.07), 0.004), at=(x, y, 0.003), m="veh_glass_cracked")
        p.transform(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(rnd.uniform(0, 3), 4, "Z") @ Matrix.Translation((-x, -y, 0)), vs)
    body = K.join([body, p.to_object("debris")], spec["name"])
    K.drop_unused_slots(body)
    res["body"] = body
    res["wheels"] = {}
    res["extra"]["lightsNote"] = "Static wreck: light slots kept (dead by default, can flicker), glass is veh_glass_cracked with shattered holes."
    return res


BURN_KEEP = {"veh_burnt", "veh_glass_cracked"}


def burnt_builder(spec, lod):
    res = VC.build_car(spec, lod)
    body = res["body"]
    # open every window (glass burst), then remap all materials to the burnt steel set
    with K.Edit(body) as e:
        gi = e.slot("veh_glass")
        kill = [f for f in e.bm.faces if f.material_index == gi]
        bmesh.ops.delete(e.bm, geom=kill, context="FACES")
    K.drop_unused_slots(body)
    me = body.data
    for i, m in enumerate(me.materials):
        if m and m.name not in BURN_KEEP:
            me.materials[i] = K.material("veh_burnt" if m.name not in ("veh_interior",) else "veh_burnt")
    K.dedupe_slots(body)
    # sag + warp: roof bows, body sits on the rims (tyres burnt away)
    def fn(c):
        out = c.copy()
        if c.z > 1.8:
            out.z -= 0.07 * math.cos(c.y / 2.7 * math.pi / 2) * (1 - abs(c.x) / 1.2)
        out += Vector((_noise3(c, 2.2, 1), _noise3(c, 2.2, 2), _noise3(c, 2.2, 3))) * 0.01
        return out
    deform(body, fn)
    keep = []
    for name, (wo, c) in res["wheels"].items():
        me = wo.data
        for i, m in enumerate(me.materials):
            me.materials[i] = K.material("veh_burnt")
        K.dedupe_slots(wo)
        wo.data.transform(Matrix.Translation(c))
        keep.append(wo)
    body = K.join([body] + keep, spec["name"])
    # drop onto the rims: rim lip radius ~ rim_r + 0.014
    drop = spec["wheel_r"] - (spec["rim_r"] + 0.014)
    body.data.transform(Matrix.Translation((0, 0, -drop)))
    lo, hi = K.bounds_world([body])
    body.data.transform(Matrix.Translation((0, 0, -lo[2])))
    K.drop_unused_slots(body)
    res["body"] = body
    res["wheels"] = {}
    res["extra"]["lightsNote"] = "Static burnt-out shell: no emissive slots, all veh_burnt; windows open; sits on the rims."
    return res
