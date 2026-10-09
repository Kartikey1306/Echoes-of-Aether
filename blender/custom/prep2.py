"""Reference scene for the customisation builds from the heroes_v2 remakes (Oct 2026).

  blender -b --python blender/custom/prep2.py -- <cid>

Source: the full MakeHuman-topology body of the v2 hero (the exported Unity Body is stripped under the outfit):
  kael: blender/heroes_v2/kael/blends/kael_s6_deform.blend  BodyMH (+ skin weights incl. twist bones transferred
        from BodyFull, its subdivided full-body twin)
  lyra: blender/heroes_v2/giva/out/giva_rig.blend           Body
The result has the same layout as prep.py (rig <Name>, <Name>.body with m_* / x_* keys, <Name>.high-poly eyes, the
Unity hero meshes as U_*, attribute 'exposed' = vertex lies on the exported Body surface) -> cache/<cid>_ref.blend.
"""
import bpy, os, sys, json, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from prep import fbx_bones
sys.path.insert(0, os.path.join(C.HERE, "lib"))
from meshutil import SurfaceBinding

V2 = os.path.join(C.ROOT, "heroes_v2")
CFG = {
    "kael": dict(src=os.path.join(V2, "kael", "blends", "kael_s6_deform.blend"), body="BodyMH", wsrc="BodyFull", eyes="Eyes"),
    "lyra": dict(src=os.path.join(V2, "giva", "out", "giva_rig.blend"), body="Body", wsrc=None, eyes="Eyes"),
}


def mesh_co(o):
    a = np.empty(len(o.data.vertices) * 3); o.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def transfer_weights(dst, src):
    """Replace dst's mixamorig groups with weights interpolated from the nearest src face (barycentric)."""
    sco = mesh_co(src)
    dco = mesh_co(dst)
    bind = SurfaceBinding(src, sco, dco, max_dist=0.1)
    names = {g.index: g.name for g in src.vertex_groups if g.name.startswith("mixamorig:")}
    W = np.zeros((len(sco), len(names)))
    col = {gi: k for k, gi in enumerate(names)}
    for v in src.data.vertices:
        for g in v.groups:
            if g.group in col:
                W[v.index, col[g.group]] = g.weight
    Wd = (bind.W[..., None] * W[bind.I]).sum(1)
    for g in list(dst.vertex_groups):
        if g.name.startswith("mixamorig:"):
            dst.vertex_groups.remove(g)
    # top-4 influences, normalised
    order = np.argsort(-Wd, axis=1)[:, :4]
    top = np.take_along_axis(Wd, order, 1)
    top[top < 0.01] = 0
    top = top / np.maximum(top.sum(1, keepdims=True), 1e-9)
    gl = list(names.values())
    groups = {}
    for vi in range(len(dco)):
        for k in range(4):
            w = top[vi, k]
            if w <= 0:
                continue
            n = gl[order[vi, k]]
            g = groups.get(n) or groups.setdefault(n, dst.vertex_groups.new(name=n))
            g.add([vi], float(w), "REPLACE")
    print("WEIGHTS transferred", len(groups), "groups; max bind dist mm", round(float(bind.dist.max()) * 1000, 2))


def main():
    cid = C.args()[0]
    cfg = CFG[cid]
    H = C.HEROES[cid]
    cname = H["name"]
    bpy.ops.wm.open_mainfile(filepath=cfg["src"])
    rig = bpy.data.objects[cname]
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    body = bpy.data.objects[cfg["body"]]
    if cfg["wsrc"]:
        transfer_weights(body, bpy.data.objects[cfg["wsrc"]])
    keep = {cfg["body"]: cname + ".body", cfg["eyes"]: cname + ".high-poly"}
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
        elif o.type not in ("MESH", "ARMATURE"):
            bpy.data.objects.remove(o, do_unlink=True)
    for old, new in keep.items():
        o = bpy.data.objects[old]
        o.name = new
        o.data.name = new
        o.parent = rig
        for m in list(o.modifiers):
            if m.type != "ARMATURE":
                o.modifiers.remove(m)
        if not any(m.type == "ARMATURE" for m in o.modifiers):
            mm = o.modifiers.new("Armature", "ARMATURE"); mm.object = rig
    body = bpy.data.objects[cname + ".body"]
    for a in [o for o in bpy.data.objects if o.type == "ARMATURE" and o is not rig]:
        bpy.data.objects.remove(a, do_unlink=True)
    # Unity hero
    existing = set(bpy.data.objects)
    fbx = os.path.join(C.UNITY_CHARS, cname, cname + ".fbx")
    bpy.ops.import_scene.fbx(filepath=fbx, use_custom_normals=True, ignore_leaf_bones=False, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in existing]
    urig = next(o for o in new if o.type == "ARMATURE")
    dmax = max(((urig.matrix_world @ b.head_local) - (rig.matrix_world @ rig.data.bones[b.name].head_local)).length
               for b in urig.data.bones if b.name in rig.data.bones)
    missing = [b.name for b in urig.data.bones if b.name not in rig.data.bones]
    print("BONE head max diff (m)", round(dmax, 6), "bones missing in ref rig", missing)
    for o in new:
        if o.type != "MESH":
            continue
        n = o.name.split(".")[0]
        if n.startswith(("Hair_", "Facial_")):
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw, shape_keys=True)
        o.matrix_world = Matrix.Identity(4)
        o.name = "U_" + n
        o.data.name = o.name
        o.parent = rig
        o.matrix_parent_inverse = rig.matrix_world.inverted()
        for m in o.modifiers:
            if m.type == "ARMATURE":
                m.object = rig
    bpy.data.objects.remove(urig, do_unlink=True)
    ub = bpy.data.objects["U_Body"]
    uco = mesh_co(ub)
    tree = BVHTree.FromPolygons([Vector(c) for c in uco], [list(p.vertices) for p in ub.data.polygons])
    co = mesh_co(body)
    d = np.array([tree.find_nearest(Vector(p), 0.05)[3] if tree.find_nearest(Vector(p), 0.05)[0] is not None else 1.0 for p in co])
    exposed = (d < 0.0025).astype(np.float32)
    at = body.data.attributes.get("exposed") or body.data.attributes.new("exposed", "FLOAT", "POINT")
    at.data.foreach_set("value", exposed)
    hd = np.array([0.0])
    print("EXPOSED", int(exposed.sum()), "of", len(co), "| distance to exported Body (exposed verts) median mm",
          round(float(np.median(d[exposed > 0])) * 1000, 3))
    bones, settings = fbx_bones(fbx)
    hb = rig.data.bones["mixamorig:Head"]
    p = C.C_B2F @ (rig.matrix_world @ hb.head_local)
    g = bones["mixamorig:Head"]["global"]
    scale = Vector((g[3], g[7], g[11])).length / p.length
    info = {"cid": cid, "fbx": fbx, "unit_scale": scale, "source": cfg["src"],
            "bones": {n: b for n, b in bones.items() if n.startswith("mixamorig:") or b["parent"] is None}, "bone_diff": dmax}
    with open(os.path.join(C.CACHE, f"{cid}_ref.json"), "w") as f:
        json.dump(info, f, indent=0, default=float)
    print("SHAPES", [k.name for k in body.data.shape_keys.key_blocks][:8], "...", len(body.data.shape_keys.key_blocks))
    print("GROUPS twist", [g.name for g in body.vertex_groups if "Twist" in g.name])
    bpy.ops.wm.save_as_mainfile(filepath=C.ref_path(cid), compress=True)
    print("SAVED", C.ref_path(cid), sorted(o.name for o in bpy.data.objects))


if __name__ == "__main__":
    main()
