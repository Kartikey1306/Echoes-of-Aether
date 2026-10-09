"""Build + export vehicles to Assets/Art/Vehicles/Models/<Name>.fbx and write out/records/<Name>.json.

Blender -b --factory-startup --python build_vehicles.py -- [Name ...]

FBX layout (Unity axes after import: +Z front, +Y up, metres, pivot = ground centre):
  <Name>_LOD0 / _LOD1 / _LOD2              body meshes (root level, identity transform)
  Wheel_FL ... (empty at the wheel centre)   -> Wheel_FL_LOD0/1/2 meshes (identity local transform)
  Thruster_* (empty at the pod pivot)        -> Thruster_*_LOD0/1/2
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import vehicles  # noqa: E402
import vkit as K  # noqa: E402
import vpaths  # noqa: E402

LOD_RATIO = (1.0, 0.40, 0.12)


def argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def total_tris(objs):
    return sum(K.tris(o) for o in objs if o.type == "MESH")


def build_one(name):
    t0 = time.time()
    K.reset()
    spec = vehicles.spec(name)
    lods = []
    pivots = {}       # part name -> (empty object, build-space centre, kind)
    meta = None
    T0 = None
    for lod in (0, 1, 2):
        res = vehicles.build(name, lod)
        body = res["body"]
        body.name = f"{name}_LOD{lod}"
        body.data.name = body.name
        parts = []
        for kind, group in (("wheel", res.get("wheels", {})), ("thruster", res.get("thrusters", {}))):
            for pn, (ob, c) in group.items():
                ob.name = f"{pn}_LOD{lod}"
                if pn not in pivots:
                    em = bpy.data.objects.new(pn, None)
                    em.empty_display_type = "ARROWS"
                    em.empty_display_size = 0.3
                    bpy.context.scene.collection.objects.link(em)
                    em.location = c
                    em.name = pn
                    pivots[pn] = (em, Vector(c), kind)
                ob.name = f"{pn}_LOD{lod}"
                ob.data.name = ob.name
                ob.parent = pivots[pn][0]
                ob.matrix_parent_inverse = Matrix.Identity(4)
                ob.location = (0, 0, 0)
                parts.append(ob)
        objs = [body] + parts
        tot = total_tris(objs)
        if lod == 0:
            T0 = tot
            meta = res
        else:
            target = int(T0 * LOD_RATIO[lod])
            if tot > target * 1.05:
                pt = total_tris(parts)
                K.decimate_to(body, max(200, target - pt), sym=True)
                tot = total_tris(objs)
            if tot > target * 1.08 and parts:
                for o in parts:  # still over: thin the parts proportionally
                    K.decimate_to(o, int(K.tris(o) * target / tot), sym=False)
        for o in objs:
            K.cleanup(o)
            K.drop_unused_slots(o)
            K.box_uv(o)
            K.shade(o)
        lods.append(objs)
        print(f"[build] {name} LOD{lod}: {total_tris(objs)} tris ({time.time() - t0:.1f}s)", flush=True)
    bpy.context.view_layer.update()
    # ---------------------------------------------------------------- ground: lowest point of LOD0 (pods / tyres / hull) at z = 0
    lo, hi = K.bounds_world(lods[0])
    dz = float(lo[2])
    if abs(dz) > 0.001:
        for l in lods:
            l[0].data.transform(Matrix.Translation((0, 0, -dz)))
        for pn, (em, c, kind) in list(pivots.items()):
            em.location.z -= dz
            pivots[pn] = (em, Vector((c.x, c.y, c.z - dz)), kind)
        for k, pts in meta["lights"].items():
            for p in pts:
                p[2] -= dz
        spec["colliders"] = [((c[0], c[1], c[2] - dz), s_) for (c, s_) in spec.get("colliders", [])]
        bpy.context.view_layer.update()
        print(f"[build] {name}: grounded by {-dz:+.3f} m", flush=True)
    # ---------------------------------------------------------------- record (computed in build space -> Unity)
    lod0 = lods[0]
    lo, hi = K.bounds_world(lod0)
    size = hi - lo
    ctr = (lo + hi) / 2
    mats = []
    for o in lod0:
        for m in o.data.materials:
            if m and m.name not in mats:
                mats.append(m.name)
    anim = []
    for pn, (em, c, kind) in sorted(pivots.items()):
        meshes = {f"LOD{l}": f"{pn}_LOD{l}" for l in range(3)}
        a = {"name": pn, "type": kind, "pivot": K.build_to_unity(c), "meshes": meshes}
        if kind == "wheel":
            a["spinAxis"] = "local X (Unity +X = vehicle right); positive rotation rolls forward"
            a["radius"] = round(float(spec.get("wheel_r", spec.get("R", 0.4)) if "wheel_r" in spec else _bike_r(pn)), 3)
            if pn in ("Wheel_FL", "Wheel_FR", "Wheel_F"):
                a["steer"] = "local Y (yaw); calipers are on the body at the top of each disc so steering is clip-free"
        else:
            a["note"] = "pivot at the pod's centre of rotation; nozzle faces -Y (down); tilt about local X (pitch) / Z (roll)"
        anim.append(a)
    lights = {}
    for k, pts in meta["lights"].items():
        lights[k] = [K.build_to_unity(p) for p in pts]
    head = [p for k, v in lights.items() if k.startswith("head") for p in v]
    tail = [p for k, v in lights.items() if k.startswith("tail") for p in v]
    rec = {
        "name": name,
        "category": vehicles.CATEGORY[name],
        "file": f"Models/{name}.fbx",
        "meshes": {f"LOD{l}": f"{name}_LOD{l}" for l in range(3)},
        "tris": {f"LOD{l}": total_tris(lods[l]) for l in range(3)},
        "trisBody": {f"LOD{l}": K.tris(lods[l][0]) for l in range(3)},
        "size": [round(float(size[0]), 3), round(float(size[2]), 3), round(float(size[1]), 3)],
        "boundsCenter": K.build_to_unity(ctr),
        "pivot": "ground-centre",
        "materials": mats,
        "colliders": [{"type": "box", "center": K.build_to_unity(c), "size": [round(s[0], 3), round(s[2], 3), round(s[1], 3)]}
                      for (c, s) in spec.get("colliders", [])],
        "lights": {
            "headlight": _anchor(head), "taillight": _anchor(tail),
            "all": lights,
        },
        "animatedParts": anim,
        "lodTransitions": [0.30, 0.10, 0.02] if vehicles.CATEGORY[name] != "hover" or name != "HoverTruck" else [0.4, 0.15, 0.03],
        "notes": meta["extra"].get("lightsNote", ""),
    }
    # ---------------------------------------------------------------- Unity axes + export
    allobjs = [o for l in lods for o in l] + [p[0] for p in pivots.values()]
    Rz = Matrix.Rotation(math.pi, 4, "Z")
    for o in allobjs:
        if o.type == "MESH":
            o.data.transform(Rz)
            o.data.update()
        if o.parent is None:
            o.location = Rz @ o.location
    bpy.context.view_layer.update()
    path = os.path.join(vpaths.MODELS, f"{name}.fbx")
    K.export_fbx(allobjs, path)
    rec["fbxBytes"] = os.path.getsize(path)
    json.dump(rec, open(os.path.join(vpaths.RECORDS, f"{name}.json"), "w"), indent=1)
    print(f"[build] {name} exported {rec['tris']} size {rec['size']} -> {path} ({rec['fbxBytes'] / 1e6:.2f} MB, {time.time() - t0:.1f}s)", flush=True)
    return rec


def _bike_r(pn):
    import vbike
    return vbike.RF if pn == "Wheel_F" else vbike.RR


def _anchor(pts):
    if not pts:
        return None
    if len(pts) == 1:
        return {"center": pts[0]}
    xs = [p[0] for p in pts]
    return {"center": [round(sum(p[i] for p in pts) / len(pts), 3) for i in range(3)], "points": pts,
            "left": min(pts, key=lambda p: p[0]), "right": max(pts, key=lambda p: p[0])}


if __name__ == "__main__":
    names = argv() or vehicles.names()
    for n in names:
        build_one(n)
